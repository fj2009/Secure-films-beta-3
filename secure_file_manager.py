"""
Secure File Manager for ITOXCARD
====================
Gestor de archivos cifrados con control de acceso por usuarios, pensado para
usarse desde la terminal. No requiere dependencias externas: el cifrado y la
interfaz visual están implementados únicamente con la librería estándar de
Python para que funcione en cualquier entorno sin instalaciones adicionales.
"""

import argparse
import base64
import hashlib
import hmac
import json
import re
import secrets
import shutil
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from typing import Dict, List, Optional

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = None
    filedialog = None


# --------------------------------------------------------------------------- #
# Estilo visual (sin dependencias externas)
# --------------------------------------------------------------------------- #

class TextStyle:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"


def _supports_color() -> bool:
    return sys.stdout.isatty()


def _stylize(text: str, style: str) -> str:
    if not _supports_color():
        return text
    return f"{style}{text}{TextStyle.RESET}"


def success(msg: str) -> None:
    print(_stylize("✓ ", TextStyle.GREEN + TextStyle.BOLD) + msg)


def error(msg: str) -> None:
    print(_stylize("✗ ", TextStyle.RED + TextStyle.BOLD) + msg, file=sys.stderr)


def warning(msg: str) -> None:
    print(_stylize("⚠ ", TextStyle.YELLOW + TextStyle.BOLD) + msg)


def info(msg: str) -> None:
    print(_stylize("ℹ ", TextStyle.CYAN + TextStyle.BOLD) + msg)


def print_banner() -> None:
    title = "Secure File Manager"
    subtitle = "Espacio seguro para tus archivos cifrados"
    width = max(len(title), len(subtitle)) + 12
    border_top = f"╔{'═' * width}╗"
    border_bottom = f"╚{'═' * width}╝"
    title_line = f"║  {('🔐 ' + title).center(width - 4)}  ║"
    subtitle_line = f"║  {subtitle.center(width - 4)}  ║"
    divider = f"║  {'─' * (width - 4)}  ║"

    print(_stylize(border_top, TextStyle.CYAN))
    print(_stylize(title_line, TextStyle.CYAN + TextStyle.BOLD))
    print(_stylize(divider, TextStyle.CYAN))
    print(_stylize(subtitle_line, TextStyle.CYAN + TextStyle.DIM))
    print(_stylize(border_bottom, TextStyle.CYAN))
    print(_stylize("  Gestiona usuarios, archivos cifrados y permisos con estilo moderno.", TextStyle.GREEN))
    print(_stylize("  Usa las teclas numéricas para seleccionar una opción del menú.", TextStyle.DIM))
    print()


def print_table(title: str, headers: List[str], rows: List[List[str]]) -> None:
    """Dibuja una tabla con bordes Unicode, sin dependencias externas."""
    if title:
        print(_stylize(f"\n{title}", TextStyle.BOLD + TextStyle.MAGENTA))
        print(_stylize("─" * len(title), TextStyle.MAGENTA))

    if not rows:
        print(_stylize("  (sin registros)", TextStyle.DIM))
        return

    str_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cells: List[str]) -> str:
        parts = [f" {cell.ljust(widths[i])} " for i, cell in enumerate(cells)]
        return "│" + "│".join(parts) + "│"

    top = "┌" + "┬".join("─" * (w + 2) for w in widths) + "┐"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 2) for w in widths) + "┘"

    print(_stylize(top, TextStyle.CYAN))
    print(_stylize(fmt_row(headers), TextStyle.BOLD + TextStyle.CYAN))
    print(_stylize(mid, TextStyle.CYAN))
    for row in str_rows:
        print(fmt_row(row))
    print(_stylize(bot, TextStyle.CYAN))


class Spinner:
    """Spinner animado (o mensaje estático si la salida no es una terminal)."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message: str):
        self.message = message
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._interactive = sys.stdout.isatty()
        self._start_time = 0.0

    def __enter__(self) -> "Spinner":
        self._start_time = time.perf_counter()
        if self._interactive:
            self._thread = threading.Thread(target=self._animate, daemon=True)
            self._thread.start()
        else:
            print(f"{self.message}...")
        return self

    def _animate(self) -> None:
        i = 0
        while not self._stop_event.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r{_stylize(frame, TextStyle.CYAN)} {self.message}...")
            sys.stdout.flush()
            i += 1
            time.sleep(0.08)

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        elapsed = time.perf_counter() - self._start_time
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()
            sys.stdout.write("\r" + " " * (len(self.message) + 24) + "\r")
        if exc_type is None:
            success(f"{self.message} — listo ({elapsed:.2f}s)")
        return False


def confirm_action(question: str, default: bool = False) -> bool:
    suffix = " [S/n]" if default else " [s/N]"
    while True:
        try:
            answer = input(_stylize(f"⚠ {question}{suffix}: ", TextStyle.YELLOW)).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not answer:
            return default
        if answer in ("s", "si", "sí", "y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Responde 's' (sí) o 'n' (no).")


def human_size(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} PB"


def format_dt(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M UTC")
    except (ValueError, TypeError):
        return iso_str


def password_strength_warning(password: str) -> Optional[str]:
    issues = []
    if len(password) < 10:
        issues.append("menos de 10 caracteres")
    if password.lower() == password or password.upper() == password:
        issues.append("no combina mayúsculas y minúsculas")
    if not any(char.isdigit() for char in password):
        issues.append("no incluye números")
    if issues:
        return "Contraseña débil (" + ", ".join(issues) + "). Considera una más robusta."
    return None


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


# --------------------------------------------------------------------------- #
# Utilidades de fecha
# --------------------------------------------------------------------------- #

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _derive_password_key(password: str, salt: bytes, purpose: bytes, length: int = 32) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt + purpose, 200_000, dklen=length)


def _pbkdf2_hash(password: str, salt: bytes) -> str:
    digest = _derive_password_key(password, salt, b"password")
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def _derive_key_material(master_key: bytes, salt: bytes, purpose: bytes, length: int = 32) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", master_key, salt + purpose, 200_000, dklen=length)


def _encrypt_master_key(master_key: bytes, password: str, salt: bytes) -> str:
    kek = _derive_password_key(password, salt, b"master-key")
    return base64.urlsafe_b64encode(encrypt_bytes(master_key, kek)).decode("utf-8")


def _decrypt_master_key(user: "User", password: str) -> bytes:
    if not user.wrapped_master_key:
        raise RuntimeError("El usuario no tiene clave maestra envuelta.")
    salt = base64.urlsafe_b64decode(user.salt.encode("utf-8"))
    kek = _derive_password_key(password, salt, b"master-key")
    return decrypt_bytes(base64.urlsafe_b64decode(user.wrapped_master_key.encode("utf-8")), kek)


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    if not key:
        raise ValueError("La clave de cifrado no puede estar vacía.")
    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    stream_key = _derive_key_material(key, salt, b"stream")
    mac_key = _derive_key_material(key, salt, b"mac", length=32)

    ciphertext = bytearray()
    for offset in range(0, len(data), 32):
        block = hashlib.sha256(stream_key + offset.to_bytes(8, "big")).digest()
        chunk = data[offset:offset + 32]
        ciphertext.extend(byte ^ mask for byte, mask in zip(chunk, block))

    mac = hmac.new(mac_key, salt + nonce + bytes(ciphertext), hashlib.sha256).digest()
    return b"PSM1" + salt + nonce + mac + bytes(ciphertext)


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    if len(blob) < 64:
        raise ValueError("El contenido cifrado es demasiado corto.")
    if blob[:4] != b"PSM1":
        raise ValueError("Formato de cifrado no soportado.")

    salt = blob[4:20]
    nonce = blob[20:32]
    received_mac = blob[32:64]
    ciphertext = blob[64:]
    stream_key = _derive_key_material(key, salt, b"stream")
    mac_key = _derive_key_material(key, salt, b"mac", length=32)
    expected_mac = hmac.new(mac_key, salt + nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(expected_mac, received_mac):
        raise ValueError("El contenido cifrado ha sido alterado o la clave es incorrecta.")

    plaintext = bytearray()
    for offset in range(0, len(ciphertext), 32):
        block = hashlib.sha256(stream_key + offset.to_bytes(8, "big")).digest()
        chunk = ciphertext[offset:offset + 32]
        plaintext.extend(byte ^ mask for byte, mask in zip(chunk, block))

    return bytes(plaintext)


# --------------------------------------------------------------------------- #
# Modelos de datos
# --------------------------------------------------------------------------- #

@dataclass
class User:
    username: str
    password_hash: str
    salt: str
    wrapped_master_key: Optional[str] = None
    is_admin: bool = False
    created_at: str = field(default_factory=_now_iso)


@dataclass
class FileRecord:
    id: str
    original_name: str
    stored_name: str
    allowed_users: List[str]
    created_at: str = field(default_factory=_now_iso)


# --------------------------------------------------------------------------- #
# Lógica principal
# --------------------------------------------------------------------------- #

class SecureAccessManager:
    def __init__(self, storage_dir: Path):
        self.storage_dir = storage_dir
        self.users_file = self.storage_dir / "users.json"
        self.files_file = self.storage_dir / "files.json"
        self.master_key_file = self.storage_dir / "master.key"
        self.encrypted_dir = self.storage_dir / "encrypted"
        self.decrypted_dir = self.storage_dir / "descifrados"

        self.users: Dict[str, User] = {}
        self.files: Dict[str, FileRecord] = {}
        self.master_key: Optional[bytes] = None
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        if not self.storage_dir.exists():
            return
        if self.master_key_file.exists():
            raw = self.master_key_file.read_bytes()
            if len(raw) == 32:
                self.master_key = raw
        if self.users_file.exists():
            data = json.loads(self.users_file.read_text(encoding="utf-8"))
            self.users = {item["username"]: User(**item) for item in data}
        if self.files_file.exists():
            data = json.loads(self.files_file.read_text(encoding="utf-8"))
            self.files = {item["id"]: FileRecord(**item) for item in data}
        self._loaded = True

    def _save(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.encrypted_dir.mkdir(parents=True, exist_ok=True)
        self.decrypted_dir.mkdir(parents=True, exist_ok=True)
        if self.master_key_file.exists():
            try:
                self.master_key_file.unlink()
            except OSError:
                pass
        self.users_file.write_text(
            json.dumps([asdict(user) for user in self.users.values()], indent=2), encoding="utf-8"
        )
        self.files_file.write_text(
            json.dumps([asdict(file_rec) for file_rec in self.files.values()], indent=2), encoding="utf-8"
        )

    def init_storage(self, admin_username: str, admin_password: str) -> None:
        if self.storage_dir.exists() and any(self.storage_dir.iterdir()):
            raise RuntimeError(f"El directorio de almacenamiento '{self.storage_dir}' ya existe y no está vacío.")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.encrypted_dir.mkdir(parents=True, exist_ok=True)
        self.decrypted_dir.mkdir(parents=True, exist_ok=True)
        self.master_key = secrets.token_bytes(32)
        self.users = {}
        self.files = {}
        self._add_user(admin_username, admin_password, is_admin=True)
        self._save()
        success(f"Espacio seguro inicializado en '{self.storage_dir}'. Usuario administrador: '{admin_username}'.")

    def _add_user(self, username: str, password: str, is_admin: bool = False) -> User:
        username = username.strip().lower()
        if not USERNAME_PATTERN.match(username):
            raise ValueError(
                "El nombre de usuario debe tener entre 3 y 32 caracteres "
                "(letras, números, '_', '.' o '-')."
            )
        if not password:
            raise ValueError("La contraseña no puede estar vacía.")
        if username in self.users:
            raise ValueError(f"El usuario '{username}' ya existe.")
        salt = secrets.token_bytes(16)
        password_hash = _pbkdf2_hash(password, salt)
        user = User(
            username=username,
            password_hash=password_hash,
            salt=base64.urlsafe_b64encode(salt).decode("utf-8"),
            wrapped_master_key=None,
            is_admin=is_admin,
        )
        if self.master_key is not None:
            user.wrapped_master_key = _encrypt_master_key(
                self.master_key,
                password,
                salt,
            )
        self.users[username] = user
        return user

    def add_user(self, admin_username: str, admin_password: str, username: str, password: str, is_admin: bool = False) -> User:
        self._load()
        admin_user = self._require_admin(admin_username, admin_password)
        self._load_master_key_for_user(admin_user, admin_password)
        user = self._add_user(username, password, is_admin=is_admin)
        self._save()
        success(f"Usuario '{username}' añadido correctamente.")
        return user

    def remove_user(self, admin_username: str, admin_password: str, username: str) -> None:
        self._load()
        self._require_admin(admin_username, admin_password)
        username = username.strip().lower()
        if username not in self.users:
            raise ValueError(f"El usuario '{username}' no existe.")
        for file_rec in self.files.values():
            if username in file_rec.allowed_users:
                file_rec.allowed_users.remove(username)
        del self.users[username]
        self._save()
        success(f"Usuario '{username}' eliminado y retirado de las listas de acceso.")

    def authorize_user(self, admin_username: str, admin_password: str, file_name: str, username: str) -> None:
        self._load()
        self._require_admin(admin_username, admin_password)
        record = self._find_file_record(file_name)
        username = username.strip().lower()
        if username not in self.users:
            raise ValueError(f"El usuario '{username}' no existe.")
        if username in record.allowed_users:
            info(f"El usuario '{username}' ya tenía acceso al archivo '{record.original_name}'.")
            return
        record.allowed_users.append(username)
        self._save()
        success(f"Usuario '{username}' autorizado para acceder a '{record.original_name}'.")

    def revoke_user(self, admin_username: str, admin_password: str, file_name: str, username: str) -> None:
        self._load()
        self._require_admin(admin_username, admin_password)
        record = self._find_file_record(file_name)
        username = username.strip().lower()
        if username not in record.allowed_users:
            info(f"El usuario '{username}' no tenía acceso al archivo '{record.original_name}'.")
            return
        record.allowed_users.remove(username)
        self._save()
        success(f"Acceso revocado para '{username}' en el archivo '{record.original_name}'.")

    def change_password(self, username: str, current_password: str, new_password: str) -> None:
        self._load()
        user = self._require_user(username, current_password)
        self._load_master_key_for_user(user, current_password)
        if not new_password:
            raise ValueError("La nueva contraseña no puede estar vacía.")
        salt = secrets.token_bytes(16)
        user.salt = base64.urlsafe_b64encode(salt).decode("utf-8")
        user.password_hash = _pbkdf2_hash(new_password, salt)
        user.wrapped_master_key = _encrypt_master_key(self.master_key, new_password, salt)
        self._save()
        success(f"Contraseña actualizada para el usuario '{username}'.")

    def encrypt_file(
        self,
        admin_username: str,
        admin_password: str,
        source_path: Path,
        allowed_usernames: List[str],
        remove_original: bool = True,
    ) -> FileRecord:
        self._load()
        admin_user = self._require_admin(admin_username, admin_password)
        self._load_master_key_for_user(admin_user, admin_password)
        if not source_path.exists() or not source_path.is_file():
            raise ValueError(f"No se encontró el archivo de origen: {source_path}")
        allowed_users = [username.strip().lower() for username in allowed_usernames if username.strip()]
        if not allowed_users:
            raise ValueError("Debe indicar al menos un usuario autorizado.")
        for username in allowed_users:
            if username not in self.users:
                raise ValueError(f"El usuario autorizado '{username}' no existe.")
        if self.master_key is None:
            raise RuntimeError("No se encontró la clave maestra. Inicializa el espacio seguro primero.")

        record_id = uuid.uuid4().hex
        stored_name = f"{record_id}.enc"
        destination = self.encrypted_dir / stored_name
        original_size = source_path.stat().st_size

        with Spinner(f"Cifrando '{source_path.name}' ({human_size(original_size)})"):
            data = source_path.read_bytes()
            destination.write_bytes(encrypt_bytes(data, self.master_key))
            if remove_original:
                source_path.unlink()

        record = FileRecord(
            id=record_id,
            original_name=source_path.name,
            stored_name=stored_name,
            allowed_users=allowed_users,
        )
        self.files[record.id] = record
        self._save()
        info(f"Usuarios con acceso: {', '.join(allowed_users)}")
        if remove_original:
            warning(f"El archivo original '{source_path.name}' fue eliminado tras el cifrado.")
        return record

    def decrypt_file(self, file_name: str, username: str, password: str, output_path: Optional[Path] = None) -> Path:
        self._load()
        user = self._require_user(username, password)
        self._load_master_key_for_user(user, password)
        record = self._find_file_record(file_name)
        if user.username not in record.allowed_users:
            raise PermissionError(f"El usuario '{user.username}' no tiene permiso para acceder a '{record.original_name}'.")
        source = self.encrypted_dir / record.stored_name
        if not source.exists():
            raise FileNotFoundError(f"El archivo encriptado no existe: {source}")
        if self.master_key is None:
            raise RuntimeError("No se encontró la clave maestra. Inicializa el espacio seguro primero.")

        if output_path is None:
            self.decrypted_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.decrypted_dir / record.original_name
        elif output_path.is_dir():
            output_path = output_path / record.original_name

        with Spinner(f"Descifrando '{record.original_name}'"):
            try:
                decrypted_data = decrypt_bytes(source.read_bytes(), self.master_key)
            except ValueError as exc:
                raise RuntimeError(
                    "No se pudo descifrar el archivo: la clave maestra no coincide o el archivo está dañado."
                ) from exc
            output_path.write_bytes(decrypted_data)

        self.files.pop(record.id, None)
        self._save()
        info(f"Guardado en: {output_path} ({human_size(output_path.stat().st_size)})")
        return output_path

    def list_users(self) -> List[User]:
        self._load()
        return sorted(self.users.values(), key=lambda u: u.username)

    def list_files(self) -> List[FileRecord]:
        self._load()
        return sorted(self.files.values(), key=lambda f: f.original_name)

    def status(self) -> dict:
        self._load()
        total_size = 0
        for record in self.files.values():
            path = self.encrypted_dir / record.stored_name
            if path.exists():
                total_size += path.stat().st_size
        disk_usage = shutil.disk_usage(self.storage_dir) if self.storage_dir.exists() else None
        return {
            "storage_dir": str(self.storage_dir.resolve()) if self.storage_dir.exists() else str(self.storage_dir),
            "initialized": self.master_key is not None,
            "total_users": len(self.users),
            "total_admins": sum(1 for u in self.users.values() if u.is_admin),
            "total_files": len(self.files),
            "total_size_bytes": total_size,
            "free_disk_bytes": disk_usage.free if disk_usage else None,
        }

    def _require_admin(self, username: str, password: str) -> User:
        user = self._require_user(username, password)
        if not user.is_admin:
            raise PermissionError(f"El usuario '{username}' no tiene privilegios de administrador.")
        return user

    def _load_master_key_for_user(self, user: User, password: str) -> bytes:
        if self.master_key is not None:
            if user.wrapped_master_key is None:
                salt = base64.urlsafe_b64decode(user.salt.encode("utf-8"))
                user.wrapped_master_key = _encrypt_master_key(self.master_key, password, salt)
                self._save()
            if self.master_key_file.exists():
                try:
                    self.master_key_file.unlink()
                except OSError:
                    pass
            return self.master_key

        if not user.wrapped_master_key:
            raise RuntimeError(
                "No se encontró la clave maestra envuelta para el usuario."
            )

        try:
            self.master_key = _decrypt_master_key(user, password)
        except ValueError as exc:
            raise PermissionError(
                "No se pudo descifrar la clave maestra con las credenciales proporcionadas."
            ) from exc

        if self.master_key_file.exists():
            try:
                self.master_key_file.unlink()
            except OSError:
                pass

        return self.master_key

    def _require_user(self, username: str, password: str) -> User:
        self._load()
        username = username.strip().lower()
        if username not in self.users:
            raise PermissionError(f"El usuario '{username}' no está registrado.")
        user = self.users[username]
        salt = base64.urlsafe_b64decode(user.salt.encode("utf-8"))
        derived = _pbkdf2_hash(password, salt)
        if not hmac.compare_digest(derived, user.password_hash):
            raise PermissionError("Contraseña incorrecta.")
        return user

    def _find_file_record(self, file_name: str) -> FileRecord:
        self._load()
        normalized = file_name.strip()
        if normalized in self.files:
            return self.files[normalized]
        matches = [
            record for record in self.files.values()
            if record.original_name == normalized or record.stored_name == normalized
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise FileNotFoundError(f"No se encontró ningún archivo seguro con el nombre '{file_name}'.")
        raise ValueError(f"El nombre '{file_name}' corresponde a varios archivos. Usa el ID único del archivo.")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gestor de acceso a archivos cifrados")
    parser.add_argument("--storage", default="secure_store", help="Directorio donde se guarda el espacio seguro")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Inicializar el espacio seguro")
    init_parser.add_argument("--admin", required=True, help="Nombre de usuario administrador inicial")

    add_user_parser = subparsers.add_parser("add-user", help="Añadir un usuario al listado")
    add_user_parser.add_argument("--admin", required=True, help="Usuario administrador")
    add_user_parser.add_argument("--username", required=True, help="Nombre del nuevo usuario")
    add_user_parser.add_argument("--password", help="Contraseña del nuevo usuario (si se omite, se pedirá de forma segura)")
    add_user_parser.add_argument("--is-admin", action="store_true", help="Otorgar privilegios de administrador")

    remove_user_parser = subparsers.add_parser("remove-user", help="Eliminar un usuario")
    remove_user_parser.add_argument("--admin", required=True, help="Usuario administrador")
    remove_user_parser.add_argument("--username", required=True, help="Nombre de usuario a eliminar")
    remove_user_parser.add_argument("--yes", action="store_true", help="No pedir confirmación")

    change_password_parser = subparsers.add_parser("change-password", help="Cambiar la contraseña de un usuario")
    change_password_parser.add_argument("--username", required=True, help="Usuario cuya contraseña cambiará")

    encrypt_parser = subparsers.add_parser("encrypt", help="Cifrar un archivo y añadirlo al espacio seguro")
    encrypt_parser.add_argument("--admin", required=True, help="Usuario administrador")
    encrypt_parser.add_argument("--file", required=True, help="Archivo a cifrar")
    encrypt_parser.add_argument("--allowed", required=True, help="Usuarios autorizados, separados por comas")
    encrypt_parser.add_argument("--keep-original", action="store_true", help="Conservar el archivo original después de cifrarlo")
    encrypt_parser.add_argument("--yes", action="store_true", help="No pedir confirmación al eliminar el original")

    decrypt_parser = subparsers.add_parser("decrypt", help="[DESHABILITADO] Descifrar solo está disponible desde el menú interactivo del programa")
    decrypt_parser.add_argument("--file", required=True, help="[NO UTILIZADO]")
    decrypt_parser.add_argument("--username", required=True, help="[NO UTILIZADO]")
    decrypt_parser.add_argument("--output", help="[NO UTILIZADO]")
    decrypt_parser.add_argument("--yes", action="store_true", help="[NO UTILIZADO]")

    authorize_parser = subparsers.add_parser("authorize", help="Autorizar un usuario para acceder a un archivo")
    authorize_parser.add_argument("--admin", required=True, help="Usuario administrador")
    authorize_parser.add_argument("--file", required=True, help="Archivo seguro al que añadir acceso")
    authorize_parser.add_argument("--username", required=True, help="Usuario a autorizar")

    revoke_parser = subparsers.add_parser("revoke", help="Revocar el acceso de un usuario a un archivo")
    revoke_parser.add_argument("--admin", required=True, help="Usuario administrador")
    revoke_parser.add_argument("--file", required=True, help="Archivo seguro al que revocar acceso")
    revoke_parser.add_argument("--username", required=True, help="Usuario a revocar")
    revoke_parser.add_argument("--yes", action="store_true", help="No pedir confirmación")

    subparsers.add_parser("list-users", help="Mostrar todos los usuarios registrados")
    subparsers.add_parser("list-files", help="Mostrar los archivos almacenados y quién puede acceder")
    subparsers.add_parser("status", help="Mostrar un resumen del espacio seguro")

    return parser


def parse_arguments() -> argparse.Namespace:
    return build_parser().parse_args()


def prompt_password(prompt_text: str) -> str:
    try:
        return getpass(prompt_text)
    except Exception as exc:
        raise RuntimeError("No se pudo leer la contraseña. Ejecuta el comando en una terminal interactiva.") from exc


def prompt_value(prompt_text: str) -> str:
    while True:
        try:
            value = input(_stylize(f"➜ {prompt_text}: ", TextStyle.YELLOW + TextStyle.BOLD)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise RuntimeError("Operación cancelada por el usuario.")
        if value:
            return value
        error("Este campo no puede estar vacío.")


def prompt_new_password(label: str) -> str:
    """Pide una contraseña nueva dos veces (verificación) y avisa si es débil."""
    while True:
        pw1 = prompt_password(f"{label}: ")
        if not pw1:
            error("La contraseña no puede estar vacía.")
            continue
        pw2 = prompt_password("Confirma la contraseña: ")
        if pw1 != pw2:
            error("Las contraseñas no coinciden. Inténtalo de nuevo.")
            continue
        hint = password_strength_warning(pw1)
        if hint:
            warning(hint)
        return pw1


def select_file_with_dialog(title: str, initialdir: Optional[Path] = None) -> Optional[Path]:
    if tk is None or filedialog is None:
        warning("No se dispone de un diálogo nativo. Introduce la ruta manualmente.")
        return None

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        initial = str(initialdir) if initialdir else None
        file_path = filedialog.askopenfilename(title=title, initialdir=initial)
        root.destroy()
        if not file_path:
            return None
        return Path(file_path)
    except Exception:
        warning("Error al abrir el selector de archivos. Introduce la ruta manualmente.")
        return None


def print_menu() -> None:
    print(_stylize("\n╭──────────────────────────╮", TextStyle.MAGENTA + TextStyle.BOLD))
    print(_stylize("│      MENÚ PRINCIPAL      │", TextStyle.MAGENTA + TextStyle.BOLD))
    print(_stylize("╰──────────────────────────╯", TextStyle.MAGENTA + TextStyle.BOLD))
    options = [
        ("1", "Inicializar espacio seguro"),
        ("2", "Añadir usuario"),
        ("3", "Eliminar usuario"),
        ("4", "Cambiar contraseña"),
        ("5", "Cifrar archivo"),
        ("6", "Descifrar archivo"),
        ("7", "Autorizar usuario"),
        ("8", "Revocar acceso"),
        ("9", "Listar usuarios"),
        ("10", "Listar archivos"),
        ("11", "Ver estado"),
        ("0", "Salir"),
    ]
    for number, description in options:
        label = f"  [{number}]"
        print(_stylize(label, TextStyle.GREEN + TextStyle.BOLD) + _stylize(f" {description}", TextStyle.CYAN))
    print(_stylize("\nUsa el número de opción para navegar.\n", TextStyle.DIM))


def prompt_menu_choice() -> Optional[str]:
    try:
        return input(_stylize("Selecciona una opción: ", TextStyle.YELLOW)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def run_interactive_menu(manager: SecureAccessManager) -> int:
    while True:
        print_banner()
        print_menu()
        choice = prompt_menu_choice()
        if choice is None:
            warning("Operación cancelada por el usuario.")
            return 130
        if choice == "0":
            info("Hasta pronto.")
            return 0

        if choice == "1":
            admin = prompt_value("Nombre de usuario administrador")
            password = prompt_new_password(f"Contraseña para el administrador '{admin}'")
            manager.init_storage(admin, password)
        elif choice == "2":
            admin = prompt_value("Usuario administrador")
            admin_password = prompt_password(f"Contraseña del administrador '{admin}': ")
            username = prompt_value("Nombre del nuevo usuario")
            password = prompt_new_password(f"Contraseña para el nuevo usuario '{username}'")
            manager.add_user(admin, admin_password, username, password)
        elif choice == "3":
            admin = prompt_value("Usuario administrador")
            admin_password = prompt_password(f"Contraseña del administrador '{admin}': ")
            username = prompt_value("Nombre de usuario a eliminar")
            manager.remove_user(admin, admin_password, username)
        elif choice == "4":
            username = prompt_value("Usuario")
            current_password = prompt_password(f"Contraseña actual de '{username}': ")
            new_password = prompt_new_password(f"Nueva contraseña para '{username}'")
            manager.change_password(username, current_password, new_password)
        elif choice == "5":
            admin = prompt_value("Usuario administrador")
            admin_password = prompt_password(f"Contraseña del administrador '{admin}': ")
            file_path = select_file_with_dialog("Selecciona el archivo a cifrar")
            if file_path is None:
                file_path = Path(prompt_value("Ruta del archivo a cifrar"))
            allowed = prompt_value("Usuarios autorizados (separados por comas)")
            allowed_users = [user.strip() for user in allowed.split(",") if user.strip()]
            manager.encrypt_file(admin, admin_password, file_path, allowed_users)
        elif choice == "6":
            username = prompt_value("Usuario")
            password = prompt_password(f"Contraseña del usuario '{username}': ")
            encrypted_file = select_file_with_dialog(
                "Selecciona el archivo cifrado a descifrar",
                initialdir=manager.encrypted_dir,
            )
            if encrypted_file is not None:
                file_name = encrypted_file.name
            else:
                file_name = prompt_value("Nombre o ID del archivo seguro")
            manager.decrypt_file(file_name, username, password)
        elif choice == "7":
            admin = prompt_value("Usuario administrador")
            admin_password = prompt_password(f"Contraseña del administrador '{admin}': ")
            file_name = prompt_value("Archivo seguro")
            username = prompt_value("Usuario a autorizar")
            manager.authorize_user(admin, admin_password, file_name, username)
        elif choice == "8":
            admin = prompt_value("Usuario administrador")
            admin_password = prompt_password(f"Contraseña del administrador '{admin}': ")
            file_name = prompt_value("Archivo seguro")
            username = prompt_value("Usuario a revocar")
            manager.revoke_user(admin, admin_password, file_name, username)
        elif choice == "9":
            users = manager.list_users()
            rows = [
                [u.username, "Administrador" if u.is_admin else "Usuario", format_dt(u.created_at)]
                for u in users
            ]
            print_table("👤 Usuarios registrados", ["Usuario", "Rol", "Creado"], rows)
        elif choice == "10":
            files = manager.list_files()
            rows = []
            for file_rec in files:
                enc_path = manager.encrypted_dir / file_rec.stored_name
                size = human_size(enc_path.stat().st_size) if enc_path.exists() else "N/D"
                rows.append([
                    file_rec.id[:8],
                    file_rec.original_name,
                    size,
                    ", ".join(file_rec.allowed_users) if file_rec.allowed_users else "(sin acceso)",
                    format_dt(file_rec.created_at),
                ])
            print_table("📁 Archivos seguros", ["ID", "Nombre original", "Tamaño", "Usuarios autorizados", "Creado"], rows)
        elif choice == "11":
            st = manager.status()
            rows = [
                ["Directorio", st["storage_dir"]],
                ["Inicializado", "Sí" if st["initialized"] else "No"],
                ["Usuarios totales", str(st["total_users"])],
                ["Administradores", str(st["total_admins"])],
                ["Archivos cifrados", str(st["total_files"])],
                ["Espacio ocupado", human_size(st["total_size_bytes"])],
            ]
            if st["free_disk_bytes"] is not None:
                rows.append(["Espacio libre en disco", human_size(st["free_disk_bytes"])])
            print_table("📊 Estado del espacio seguro", ["Campo", "Valor"], rows)
        else:
            error("Opción no válida. Elige un número del menú.")

        try:
            input(_stylize("\nPresiona Enter para continuar...", TextStyle.DIM))
        except (EOFError, KeyboardInterrupt):
            print()
            return 0


def main() -> int:
    print_banner()
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        return run_interactive_menu(SecureAccessManager(Path(args.storage)))

    manager = SecureAccessManager(Path(args.storage))

    try:
        if args.command == "init":
            password = prompt_new_password(f"Contraseña para el administrador '{args.admin}'")
            manager.init_storage(args.admin, password)

        elif args.command == "add-user":
            admin_password = prompt_password(f"Contraseña del administrador '{args.admin}': ")
            password = args.password or prompt_new_password(f"Contraseña para el nuevo usuario '{args.username}'")
            manager.add_user(args.admin, admin_password, args.username, password, is_admin=args.is_admin)

        elif args.command == "remove-user":
            if not args.yes and not confirm_action(f"¿Eliminar al usuario '{args.username}'? Esta acción no se puede deshacer"):
                info("Operación cancelada.")
                return 0
            admin_password = prompt_password(f"Contraseña del administrador '{args.admin}': ")
            manager.remove_user(args.admin, admin_password, args.username)

        elif args.command == "change-password":
            current_password = prompt_password(f"Contraseña actual de '{args.username}': ")
            new_password = prompt_new_password(f"Nueva contraseña para '{args.username}'")
            manager.change_password(args.username, current_password, new_password)

        elif args.command == "encrypt":
            remove_original = not args.keep_original
            if remove_original and not args.yes:
                if not confirm_action("Esto eliminará el archivo original tras cifrarlo. ¿Continuar?"):
                    info("Operación cancelada.")
                    return 0
            admin_password = prompt_password(f"Contraseña del administrador '{args.admin}': ")
            allowed = [user.strip() for user in args.allowed.split(",") if user.strip()]
            manager.encrypt_file(args.admin, admin_password, Path(args.file), allowed, remove_original=remove_original)

        elif args.command == "decrypt":
            error("❌ El descifrado SOLO está disponible desde el menú interactivo del programa.")
            error("   Ejecuta el programa sin argumentos o usa: python secure_file_manager.py")
            return 1

        elif args.command == "authorize":
            admin_password = prompt_password(f"Contraseña del administrador '{args.admin}': ")
            manager.authorize_user(args.admin, admin_password, args.file, args.username)

        elif args.command == "revoke":
            if not args.yes and not confirm_action(f"¿Revocar el acceso de '{args.username}' a '{args.file}'?"):
                info("Operación cancelada.")
                return 0
            admin_password = prompt_password(f"Contraseña del administrador '{args.admin}': ")
            manager.revoke_user(args.admin, admin_password, args.file, args.username)

        elif args.command == "list-users":
            users = manager.list_users()
            rows = [
                [u.username, "Administrador" if u.is_admin else "Usuario", format_dt(u.created_at)]
                for u in users
            ]
            print_table("👤 Usuarios registrados", ["Usuario", "Rol", "Creado"], rows)

        elif args.command == "list-files":
            files = manager.list_files()
            rows = []
            for file_rec in files:
                enc_path = manager.encrypted_dir / file_rec.stored_name
                size = human_size(enc_path.stat().st_size) if enc_path.exists() else "N/D"
                rows.append([
                    file_rec.id[:8],
                    file_rec.original_name,
                    size,
                    ", ".join(file_rec.allowed_users) if file_rec.allowed_users else "(sin acceso)",
                    format_dt(file_rec.created_at),
                ])
            print_table("📁 Archivos seguros", ["ID", "Nombre original", "Tamaño", "Usuarios autorizados", "Creado"], rows)

        elif args.command == "status":
            st = manager.status()
            rows = [
                ["Directorio", st["storage_dir"]],
                ["Inicializado", "Sí" if st["initialized"] else "No"],
                ["Usuarios totales", str(st["total_users"])],
                ["Administradores", str(st["total_admins"])],
                ["Archivos cifrados", str(st["total_files"])],
                ["Espacio ocupado", human_size(st["total_size_bytes"])],
            ]
            if st["free_disk_bytes"] is not None:
                rows.append(["Espacio libre en disco", human_size(st["free_disk_bytes"])])
            print_table("📊 Estado del espacio seguro", ["Campo", "Valor"], rows)

        else:
            raise ValueError(f"Comando desconocido: {args.command}")

    except KeyboardInterrupt:
        print()
        warning("Operación cancelada por el usuario.")
        return 130
    except Exception as exc:
        error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
