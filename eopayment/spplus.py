from decimal import Decimal
import binascii
import hmac
import hashlib
import urlparse
import urllib
import string
import datetime as dt
import logging

import Crypto.Cipher.DES
from common import PaymentCommon, URL

KEY_DES_KEY = '\x45\x1f\xba\x4f\x4c\x3f\xd4\x97'
IV = '\x30\x78\x30\x62\x2c\x30\x78\x30'
REFERENCE = 'reference'
ETAT = 'etat'
ETAT_PAIEMENT_ACCEPTE = '1'
SPCHECKOK = 'spcheckok'

def decrypt_ntkey(ntkey):
    key = binascii.unhexlify(ntkey.replace(' ',''))
    return decrypt_key(key)

def decrypt_key(key):
    CIPHER = Crypto.Cipher.DES.new(KEY_DES_KEY, Crypto.Cipher.DES.MODE_CBC, IV)
    return CIPHER.decrypt(key)

def sign_ntkey_query(ntkey, query):
    key = decrypt_ntkey(ntkey)
    data_to_sign = ''.join(y for x,y in urlparse.parse_qsl(query, True))
    return hmac.new(key[:20], data_to_sign, hashlib.sha1).hexdigest()

PAIEMENT_FIELDS = [ 'siret', REFERENCE, 'langue', 'devise', 'montant',
    'taxe', 'validite' ]

def sign_url_paiement(ntkey, query):
    if '?' in query:
        query = query[query.index('?')+1:]
    key = decrypt_ntkey(ntkey)
    data = urlparse.parse_qs(query, True)
    fields = [data.get(field,[''])[0] for field in PAIEMENT_FIELDS]
    data_to_sign = ''.join(fields)
    return hmac.new(key[:20], data_to_sign, hashlib.sha1).hexdigest()

ALPHANUM = string.letters + string.digits
SERVICE_URL = "https://www.spplus.net/paiement/init.do"
LOGGER = logging.getLogger(__name__)

class Payment(PaymentCommon):
    def __init__(self, options):
        self.cle = options['cle']
        self.siret = options['siret']
        self.devise = '978'
        self.langue = options.get('langue', 'FR')
        self.taxe = options.get('taxe', '0.00')

    def request(self, montant, email=None, next_url=None):
        reference = self.transaction_id(20, ALPHANUM, 'spplus', self.siret)
        validite = dt.date.today()+dt.timedelta(days=1)
        validite = validite.strftime('%d/%m/%Y')
        fields = { 'siret': self.siret,
                'devise': self.devise,
                'langue': self.langue,
                'taxe': self.taxe,
                'montant': str(Decimal(montant)),
                REFERENCE: reference,
                'validite': validite,
                'version': '1'}
        if email:
            fields['email'] = email
        if next_url:
            if (not next_url.startswith('http://') \
                    and not next_url.startswith('https://')) \
                       or '?' in next_url:
                   raise ValueError('next_url must be an absolute URL without parameters')
            fields['urlretour'] = next_url
        query = urllib.urlencode(fields)
        return reference, URL, '%s?%s&hmac=%s' % (SERVICE_URL, query,
                sign_ntkey_query(self.cle, query))

    def response(self, query_string):
        form = urlparse.parse_qs(query_string)
        LOGGER.debug('received query_string %s' % query_string)
        LOGGER.debug('parsed as %s' % form)
        reference = form.get(REFERENCE)
        if not 'hmac' in form:
            return form.get('etat') == 1, reference, form, None
        else:
            try:
                signed_data, signature = query_string.rsplit('&', 1)
                _, hmac = signature.split('=', 1)
                LOGGER.debug('got signature %s' % hmac)
                computed_hmac = sign_ntkey_query(self.clem, signed_data)
                LOGGER.debug('computed signature %s' % hmac)
                result = hmac==computed_hmac \
                        and reference.get(ETAT) == ETAT_PAIEMENT_ACCEPTE
                return result, reference, form, SPCHECKOK
            except ValueError:
                return False, reference, form, SPCHECKOK

if __name__ == '__main__':
    import sys

    ntkey = '58 6d fc 9c 34 91 9b 86 3f fd 64 63 c9 13 4a 26 ba 29 74 1e c7 e9 80 79'
    payment = Payment({'cle': ntkey, 'siret': '00000000000001-01'})
    print payment.request(10)
    if len(sys.argv) > 1:
        print sign_url_paiement(ntkey, sys.argv[1])
        print sign_ntkey_query(ntkey, sys.argv[1])
    else:
        tests = [('x=coin', 'c04f8266d6ae3ce37551cce996c751be4a95d10a'),
                 ('x=coin&y=toto', 'ef008e02f8dbf5e70e83da416b0b3a345db203de')]
        for query, result in tests:
            assert sign_ntkey_query(ntkey, query) == result