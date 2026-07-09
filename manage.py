#!/usr/bin/env python
"""Django komut satırı yardımcı aracı."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django bulunamadı. Sanal ortam aktif mi ve 'pip install -r "
            "requirements.txt' çalıştırıldı mı?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
