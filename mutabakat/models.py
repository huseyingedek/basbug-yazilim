from django.db import models


class MutabakatCevap(models.Model):
    """Kullanıcının verdiği mutabakat kararı (yanıt kaydı)."""

    KARAR_MUTABIK = "mutabik"
    KARAR_ITIRAZ = "itiraz"
    KARAR_SECENEKLERI = [
        (KARAR_MUTABIK, "Mutabıkız"),
        (KARAR_ITIRAZ, "Mutabık Değiliz"),
    ]

    token = models.CharField("Bağlantı anahtarı", max_length=255)
    dokuman_id = models.CharField("Doküman ID", max_length=50, blank=True)
    cari_kod = models.CharField("Cari kod", max_length=50, blank=True)
    cari_adi = models.CharField("Cari adı", max_length=255, blank=True)

    karar = models.CharField("Karar", max_length=20, choices=KARAR_SECENEKLERI)
    mesaj = models.TextField("Mesaj / açıklama", max_length=255, blank=True)
    ad_soyad = models.CharField("Ad Soyad", max_length=150, blank=True)
    dosya = models.FileField("Ek dosya", upload_to="mutabakat_ekler/", blank=True)

    olusturulma = models.DateTimeField("Yanıt tarihi", auto_now_add=True)

    class Meta:
        verbose_name = "Mutabakat cevabı"
        verbose_name_plural = "Mutabakat cevapları"
        ordering = ["-olusturulma"]

    def __str__(self):
        return f"{self.cari_adi or self.token} — {self.get_karar_display()}"
