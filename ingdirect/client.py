# -*- coding: utf-8 -*-
"""
Fonctionnalité permettant de faire les requêtes HTTP
vers ING Direct <https://www.ing.fr>
"""

import requests
from urllib.parse import urljoin
import shutil
import json
import cv2 as cv
import numpy as np
import os
from PIL import Image
import json

_URL_BASE = "https://m.ing.fr/secure/api-v1/"
_URL_LOGIN = urljoin(_URL_BASE, "login/cif")
_URL_KEYPAD = urljoin(_URL_BASE, "login/keypad")
_URL_SAISIE_CODE = urljoin(_URL_BASE, "login/sca/pin")
_URL_INFOS_CLIENT = urljoin(_URL_BASE, "customer/info")
_URL_SYNTHESE_COMPTES = urljoin(_URL_BASE, "accounts")
_URL_LOGOUT = urljoin(_URL_BASE, "logout")
_TAILLE_KEYPAD_W = 680
_TAILLE_KEYPAD_H = 272
_REPERTOIRE_SCRIPT = os.path.dirname(os.path.realpath(__file__))
_REPERTOIRE_IMAGES_CHIFFRES = "images_chiffres_keypad"
_FICHIER_KEYPAD = 'keypad.png'


class Client(object):
    """Fait les requêtes avec le serveur ing.fr"""

    def __init__(self):
        """ Initialisation du client """
        self.session = requests.session()
        self.headers = {
                    'Origin': 'https://m.ing.fr',
                    'Host': 'm.ing.fr',
                    'Accept': 'Accept: application/json,text/plain, */*',
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 7.0; \
                        SM-A520F Build/NRD90M; wv) AppleWebKit/537.36 \
                        (KHTML, like Gecko) Version/4.0 \
                        Chrome/65.0.3325.109 Mobile Safari/537.36',
                    'Ingdf-Originating-Device': 'Android',
                    'Content-Type': 'application/json;charset=UTF-8',
                    }

    def _get(self, url, expected_status_code=200):
        """ Requête GET avec les bons headers """
        ret = self.session.get(url=url, headers=self.headers)
        if (ret.status_code != expected_status_code):
            raise ConnectionError(
                'Status code {status} for url {url}\n{content}'.format(
                    status=ret.status_code, url=url, content=ret.text))
        return ret

    def _get_file(self, url, path):
        """ Télécharge un fichier dans le chemin spécifié
        (incluant son nom de fichier) avec les bons headers """
        r = self.session.get(url, headers=self.headers, stream=True)
        if r.status_code == 200:
            with open(path, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
        return r

    def _post(self, url, post_data, expected_status_code=200):
        """ Requête POST avec les bons headers """
        ret = self.session.post(url, headers=self.headers, json=post_data)
        if (ret.status_code != expected_status_code):
            raise ConnectionError(
                'Status code {status} for url {url}\n{content}'.format(
                    status=ret.status_code, url=url, content=ret.text))
        return ret

    def _login(self, num_client, date_naissance):
        """ Permet de se connecter à ING Direct """

        post_data_dict = {"cif": num_client, "birthDate": date_naissance}
        r = self._post(url=_URL_LOGIN, post_data=post_data_dict)
        self.regie_id = r.json().get('regieId')
    
    def _recuperer_url_keypad(self):
        post_data_dict = {
            "keyPadSize": {
                "width": _TAILLE_KEYPAD_W,
                "height": _TAILLE_KEYPAD_H},
            "mode": ""
        }
        r = self._post(url=_URL_KEYPAD, post_data=post_data_dict)
        self.url_keypad = r.json().get('keyPadUrl')
        self.pin_positions = r.json().get('pinPositions')

    def _recuperer_keypad(self):
        """ Télécharge l'image du clavier pour saisir le code
        dans le dossier courant (sous le nom keypad.png) """
        url_keypad = self.url_keypad
        # urljoin retire "api-v1/" de l'url si url_keypad commence par un '/'
        if url_keypad[0] == '/':
            url_keypad = url_keypad[1:]
        url = urljoin(_URL_BASE, url_keypad)
        return self._get_file(url, _FICHIER_KEYPAD)

    def _code_a_saisir(self, code_complet):
        """ Renvoie les digits à saisir
        (ex : si le code et 876921, et que les pins 1,3,4 sont à saisir,
        la fonction renvoie [8,6,9]) """

        retour_code = []
        for i in range(0, 3):
            retour_code.append(int(code_complet[int(self.pin_positions[i])-1]))
        self.code_a_saisir = retour_code

        return retour_code

    def _trouver_chiffre(self, chiffre):
        """ Retourne les coordonnées x,y du centre du chiffre
        sur le keypad (ou retourne False sinon) """
        # On vérifie si l'image du keypad a déjà été récupérée
        if not hasattr(self, 'img_gray'):
            img_rgb = cv.imread(_FICHIER_KEYPAD)
            self.img_gray = cv.cvtColor(img_rgb, cv.COLOR_BGR2GRAY)
            os.remove(_FICHIER_KEYPAD)
        if chiffre not in range(0, 10):
            retour = False
        else:
            chemin_image_chiffre = os.path.join(
                                    _REPERTOIRE_SCRIPT,
                                    _REPERTOIRE_IMAGES_CHIFFRES,
                                    str(chiffre)+'.png'
                                    )
            template = cv.imread(chemin_image_chiffre, 0)
            w, h = template.shape[::-1]  # Taille de l'image du chiffre
            res = cv.matchTemplate(
                                    self.img_gray,
                                    template,
                                    cv.TM_CCOEFF_NORMED
                                    )
            min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)
            return list(max_loc)


    def _recuperer_coord_chiffres(self):
        """ Récupère la liste des coordonnées des chiffres à saisir """
        liste_coord_chiffres = []
        for digit in self.code_a_saisir:
            liste_coord_chiffres.append(self._trouver_chiffre(digit))
        self.liste_coord_chiffres = liste_coord_chiffres
        return liste_coord_chiffres

    def _saisie_code(self):
        """ Envoyer la requête de saisie du code """

        post_data_dict = {'clickPositions': self.liste_coord_chiffres}
        r = self._post(url=_URL_SAISIE_CODE, post_data=post_data_dict)
        retour_saisie_code = json.loads(r.text)
        self.headers['Ingdf-Auth-Token'] = r.headers.get('Ingdf-Auth-Token')

        return retour_saisie_code

    def _infos_client(self):
        """ Récupérer les informations client """

        r = self._get(url=_URL_INFOS_CLIENT)
        retour_infos_client = json.loads(r.text)
        self.infos_client_json = retour_infos_client

        return retour_infos_client

    def _synthese_comptes(self):
        """ Récupérer la synthèse des comptes """

        r = self._get(url=_URL_SYNTHESE_COMPTES)
        retour_synthese_comptes = json.loads(r.text)
        self.synthese_comptes_json = retour_synthese_comptes

        return retour_synthese_comptes

    def _operations_compte(self, compte_uid, max_operations=50):
        if not hasattr(self, "operations_compte"):
            self.operations_compte = {}
        if compte_uid not in self.operations_compte:
            r = self._get(url=f"{_URL_SYNTHESE_COMPTES}/{compte_uid}/transactions/after/0/limit/{max_operations}")
            self.operations_compte[compte_uid] = json.loads(r.text)

        return self.operations_compte[compte_uid]

    def _logout(self):
        """ Se déconnecter """

        r = self._post(url=_URL_LOGOUT, post_data="", expected_status_code=204)
        retour_logout = r.text

        return retour_logout
