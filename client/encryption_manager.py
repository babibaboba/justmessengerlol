import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa, padding as rsa_padding
from cryptography.hazmat.primitives import serialization, hashes

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64

class EncryptionManager:
    def __init__(self):
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        self.public_key = self.private_key.public_key()
        self.peer_public_keys = {} # {username: public_key}
        self.session_keys = {} # {username: session_key}

    def get_public_key_pem(self):
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def add_peer_public_key(self, username, public_key_pem):
        try:
            public_key = serialization.load_pem_public_key(
                public_key_pem,
                backend=default_backend()
            )
            self.peer_public_keys[username] = public_key
            return True
        except Exception as e:
            print(f"Error loading public key for {username}: {e}")
            return False

    def generate_session_key(self, username):
        if username not in self.peer_public_keys:
            return None, None
        
        session_key = os.urandom(32) # AES-256
        self.session_keys[username] = session_key
        
        peer_public_key = self.peer_public_keys[username]
        encrypted_session_key = peer_public_key.encrypt(
            session_key,
            rsa_padding.OAEP(
                mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return session_key, encrypted_session_key

    def receive_session_key(self, username, encrypted_session_key):
        try:
            session_key = self.private_key.decrypt(
                encrypted_session_key,
                rsa_padding.OAEP(
                    mgf=rsa_padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            self.session_keys[username] = session_key
            return True
        except Exception as e:
            print(f"Error decrypting session key from {username}: {e}")
            return False

    def encrypt_message(self, username, message):
        if username not in self.session_keys:
            print(f"No session key for {username}")
            return None
        
        session_key = self.session_keys[username]
        iv = os.urandom(16)
        
        cipher = Cipher(algorithms.AES(session_key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(message.encode('utf-8')) + padder.finalize()
        
        encrypted_message = encryptor.update(padded_data) + encryptor.finalize()
        
        return iv + encrypted_message

    def decrypt_message(self, username, encrypted_data):
        if username not in self.session_keys:
            print(f"No session key for {username}")
            return None
            
        session_key = self.session_keys[username]
        iv = encrypted_data[:16]
        encrypted_message = encrypted_data[16:]
        
        try:
            cipher = Cipher(algorithms.AES(session_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            
            decrypted_padded_message = decryptor.update(encrypted_message) + decryptor.finalize()
            
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            decrypted_message_bytes = unpadder.update(decrypted_padded_message) + unpadder.finalize()
            
            return decrypted_message_bytes.decode('utf-8')
        except Exception as e:
            print(f"Error decrypting message from {username}: {e}")
            return None

    @staticmethod
    def hash_password(password):
        """Hashes a password using SHA256."""
        if not password:
            return None
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(password.encode('utf-8'))
        return digest.finalize().hex()

    def _derive_key_from_password(self, password, salt):
        """Derives an AES key from a password and salt using PBKDF2."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32, # AES-256
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))

    def encrypt_with_password(self, password, data):
        """Encrypts data using a key derived from a password."""
        salt = os.urandom(16)
        key = self._derive_key_from_password(password, salt)
        iv = os.urandom(16)
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(data.encode('utf-8')) + padder.finalize()
        
        encrypted_message = encryptor.update(padded_data) + encryptor.finalize()
        
        # Return salt + iv + encrypted_message, base64 encoded for transport
        return base64.b64encode(salt + iv + encrypted_message).decode('utf-8')

    def decrypt_with_password(self, password, encrypted_data_b64):
        """Decrypts data using a key derived from a password."""
        try:
            encrypted_data = base64.b64decode(encrypted_data_b64)
            salt = encrypted_data[:16]
            iv = encrypted_data[16:32]
            encrypted_message = encrypted_data[32:]
            
            key = self._derive_key_from_password(password, salt)
            
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            
            decrypted_padded_message = decryptor.update(encrypted_message) + decryptor.finalize()
            
            unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
            decrypted_message_bytes = unpadder.update(decrypted_padded_message) + unpadder.finalize()
            
            return decrypted_message_bytes.decode('utf-8')
        except Exception as e:
            print(f"Error decrypting with password: {e}")
            return None