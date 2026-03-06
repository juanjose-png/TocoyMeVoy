"""
Configuración centralizada de logging para el proyecto Solenium.

Define:
    - WeeklyRotatingHandler: handler custom con rotación semanal.
    - LOGGING: dict de Django (aplicado via dictConfig en django.setup()).

Archivos generados en {BASE_DIR}/.logs/:
    - {mes}_semana_{WW}_{año}.log          (general, rotación semanal)
    - important.log                         (WARNING+, sin rotación)
    - {mes}_semana_{WW}_{año}_tokens.log   (tokens Gemini, rotación semanal)
"""

import os
import sys
import time
from logging.handlers import BaseRotatingHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).resolve().parent.parent  # raíz del proyecto
LOGS_DIR = str(_BASE_DIR / ".logs")

# Crear el directorio antes de que los handlers intenten abrir archivos.
os.makedirs(LOGS_DIR, exist_ok=True)


def _is_dir_writable(path: str) -> bool:
    """Verifica si el directorio es escribible creando un archivo temporal."""
    test_file = os.path.join(path, ".write_test")
    try:
        with open(test_file, "w") as f:
            f.write("")
        os.remove(test_file)
        return True
    except OSError:
        return False


_LOGS_WRITABLE = _is_dir_writable(LOGS_DIR)
if not _LOGS_WRITABLE:
    print(
        f"WARNING: El directorio de logs '{LOGS_DIR}' no es escribible. "
        "File logging deshabilitado — solo console.",
        file=sys.stderr,
    )

# ---------------------------------------------------------------------------
# Nivel de log desde variable de entorno
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# ---------------------------------------------------------------------------
# Meses en español
# ---------------------------------------------------------------------------
_MESES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


# ---------------------------------------------------------------------------
# Handler con rotación semanal
# ---------------------------------------------------------------------------
def _build_weekly_filename(base_dir: str, suffix: str = "") -> str:
    """Construye el nombre de archivo para la semana actual.

    Patrón: {base_dir}/{mes}_semana_{WW}_{YYYY}{suffix}.log
    Ejemplo: .logs/marzo_semana_09_2026.log
    """
    now = time.localtime()
    month_name = _MESES[now.tm_mon]
    week_number = time.strftime("%W", now)
    year = now.tm_year
    return os.path.join(base_dir, f"{month_name}_semana_{week_number}_{year}{suffix}.log")


class WeeklyRotatingHandler(BaseRotatingHandler):
    """Handler que rota el archivo de log cada semana.

    Hereda de BaseRotatingHandler, que provee:
        - emit() thread-safe con self.lock
        - Ciclo automático shouldRollover/doRollover

    Args:
        base_dir: Directorio donde se almacenan los logs.
        suffix: String añadido antes de .log (ej: "_tokens").
        encoding: Encoding del archivo (default utf-8).
    """

    def __init__(
        self,
        base_dir: str = LOGS_DIR,
        suffix: str = "",
        encoding: str = "utf-8",
    ):
        self.base_dir = base_dir
        self.suffix = suffix
        self._current_week = time.strftime("%W")

        os.makedirs(base_dir, exist_ok=True)

        filename = _build_weekly_filename(base_dir, suffix)
        super().__init__(filename, mode="a", encoding=encoding)

    def shouldRollover(self, record) -> int:
        """Retorna 1 si la semana cambió desde la última escritura."""
        current_week = time.strftime("%W")
        if current_week != self._current_week:
            return 1
        return 0

    def doRollover(self):
        """Cierra el stream actual y abre uno nuevo para la nueva semana."""
        if self.stream:
            self.stream.close()
            self.stream = None

        self._current_week = time.strftime("%W")
        self.baseFilename = os.path.abspath(
            _build_weekly_filename(self.base_dir, self.suffix)
        )
        self.stream = self._open()


# ---------------------------------------------------------------------------
# Handlers y loggers (condicionales según escritura de .logs/)
# ---------------------------------------------------------------------------
_handlers = {
    "console": {
        "class": "logging.StreamHandler",
        "formatter": "standard",
        "level": LOG_LEVEL,
        "stream": "ext://sys.stdout",
    },
}

_root_handlers = ["console"]
_tokens_handlers = ["console"]

if _LOGS_WRITABLE:
    _handlers["general_file"] = {
        "()": "solenium_project.logging_config.WeeklyRotatingHandler",
        "base_dir": LOGS_DIR,
        "suffix": "",
        "encoding": "utf-8",
        "formatter": "standard",
        "level": LOG_LEVEL,
    }
    _handlers["important_file"] = {
        "class": "logging.FileHandler",
        "filename": os.path.join(LOGS_DIR, "important.log"),
        "mode": "a",
        "encoding": "utf-8",
        "formatter": "standard",
        "level": "WARNING",
    }
    _handlers["tokens_file"] = {
        "()": "solenium_project.logging_config.WeeklyRotatingHandler",
        "base_dir": LOGS_DIR,
        "suffix": "_tokens",
        "encoding": "utf-8",
        "formatter": "standard",
        "level": "INFO",
    }
    _root_handlers = ["console", "general_file", "important_file"]
    _tokens_handlers = ["console", "tokens_file"]

# ---------------------------------------------------------------------------
# Django LOGGING dict
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": _handlers,
    "loggers": {
        "": {
            "handlers": _root_handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "tokens": {
            "handlers": _tokens_handlers,
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": _root_handlers,
            "level": "WARNING",
            "propagate": False,
        },
        "celery": {
            "handlers": _root_handlers,
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}
