"""
Tüm firma logolarını EReconCompanyPict'ten çekip firma_logolari/ klasörüne yazar.

Kullanım:
    python manage.py logo_guncelle

Windows Görev Zamanlayıcı ile her pazartesi akşamı çalıştırılır.
"""
from django.core.management.base import BaseCommand, CommandError

from mutabakat import logolar


class Command(BaseCommand):
    help = "Firma logolarını servisten çekip dosyaya kaydeder (haftalık)."

    def handle(self, *args, **options):
        try:
            sonuc = logolar.logolari_guncelle()
        except Exception as e:
            raise CommandError(f"Logo servisi çağrılamadı: {e}")

        self.stdout.write(f"Klasör     : {logolar.LOGO_DIR}")
        self.stdout.write(f"Bulunan    : {sonuc['bulunan']}")
        self.stdout.write(f"Kaydedilen : {sonuc['kaydedilen']}")
        if sonuc["bulunan"] == 0:
            self.stdout.write(self.style.WARNING(
                "Yanıtta COMPANY + LOGOBASE64 bulunamadı. Ham yanıtın başı:\n" + sonuc["ham"]))
            raise CommandError("Hiç logo bulunamadı.")
        self.stdout.write(self.style.SUCCESS("Logolar güncellendi."))
