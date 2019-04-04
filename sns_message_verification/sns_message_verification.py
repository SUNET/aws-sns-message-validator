
import re
import enum
import json
import logging
import base64
import requests
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.hashes import SHA1
from cryptography.exceptions import InvalidSignature
from .sns_message_type import SNSMessageType
from .exceptions import (
    InvalidSignatureVersionException,
    InvalidCertURLException,
    InvalidMessageTypeException, 
    SignatureVerificationFailureException,
)


DEFAULT_CERTIFICATE_URL_REGEX = r'^https://sns\.[-a-z0-9]+\.amazonaws\.com/'


class SNSMessageVerification:
    def __init__(self, cert_url_regex=DEFAULT_CERTIFICATE_URL_REGEX):
        self._cert_url_regex = cert_url_regex

    def _verify_signature_version(self, message):
        if message.get('SignatureVersion') != '1':
            raise InvalidSignatureVersionException('Invalid signature version. Unable to verify signature.')
    
    def _verify_cert_url(self, message):
        cert_url = message.get('SigningCertURL')
        if not cert_url:
            raise InvalidCertURLException('Could not find SigningCertURL field in message.')
        if not re.search(self._cert_url_regex, cert_url):
            raise InvalidCertURLException('Invalid certificate URL.')

    def _get_plaintext_to_sign(self, message):
        message_type = message.get('Type')
        if message_type == SNSMessageType.SubscriptionConfirmation.value or \
            message_type == SNSMessageType.UnsubscribeConfirmation.value:
            keys = ('Message', 'MessageId', 'SubscribeURL', 'Timestamp', 'Token', 'TopicArn', 'Type',)
        elif message_type == SNSMessageType.Notification.value:
            if message.get('Subject'):
                keys = ('Message', 'MessageId', 'Subject', 'Timestamp', 'TopicArn', 'Type')
            else:
                keys = ('Message', 'MessageId', 'Timestamp', 'TopicArn', 'Type',)
        pairs = [f'{key}\n{message.get(key)}' for key in keys]
        return '\n'.join(pairs) + '\n'

    def _verify_signature(self, message):
        try:
            pem = requests.get(message.get('SigningCertURL')).content
        except Exception:
            raise SignatureVerificationFailureException('Failed to fetch cert file.')

        cert = x509.load_pem_x509_certificate(pem, default_backend())
        public_key = cert.public_key()
        plaintext = self._get_plaintext_to_sign(message).encode()
        signature = base64.b64decode(message.get('Signature'))
        try:
            public_key.verify(
                signature,
                plaintext,
                PKCS1v15(),
                SHA1(),
            )
        except InvalidSignature:
            raise SignatureVerificationFailureException('Invalid signature.')

    def verify_message(self, message):
        self.verify_message_type(message.get('Type'))

        self._verify_signature_version(message)
        self._verify_cert_url(message)
        self._verify_signature(message)

    def verify_message_type(self, message_type: str):
        try:
            sns_message_type: SNSMessageType = SNSMessageType(message_type)
        except ValueError:
            raise InvalidMessageTypeException(f'{message_type} is not a valid message type.')