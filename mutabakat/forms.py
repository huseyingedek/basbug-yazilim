from django import forms


class SifreForm(forms.Form):
    """E-posta ile gelen 8 haneli doğrulama kodu."""

    sifre = forms.CharField(
        label="Doğrulama Kodu",
        min_length=4,
        max_length=16,
        widget=forms.TextInput(attrs={
            "class": "form-input",
            "placeholder": "Doğrulama kodunu giriniz",
            "inputmode": "numeric",
            "pattern": "[0-9]*",
            "maxlength": "16",
            "autocomplete": "one-time-code",
            "autofocus": "autofocus",
        }),
    )

    def clean_sifre(self):
        v = (self.cleaned_data.get("sifre") or "").strip()
        if not v.isdigit():
            raise forms.ValidationError("Kod yalnızca rakamlardan oluşmalıdır.")
        return v


class CevapForm(forms.Form):
    """Mutabıkız / Mutabık Değiliz kararının ortak formu."""

    karar = forms.ChoiceField(
        choices=[("mutabik", "Mutabıkız"), ("itiraz", "Mutabık Değiliz")],
        widget=forms.HiddenInput,
    )
    ad_soyad = forms.CharField(
        label="Ad Soyad (tercihen)",
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    mesaj = forms.CharField(
        label="Mesaj / açıklama",
        required=False,
        max_length=255,
        widget=forms.Textarea(attrs={"class": "form-input", "rows": 4,
                                     "maxlength": 255}),
    )
    dosya = forms.FileField(
        label="Dosya (tercihen)",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-file"}),
    )

    def clean(self):
        cleaned = super().clean()
        # İtirazda (mutabık değiliz) açıklama zorunlu
        if cleaned.get("karar") == "itiraz" and not cleaned.get("mesaj", "").strip():
            self.add_error("mesaj", "Mutabık olmadığınız durumda lütfen nedenini yazınız.")
        return cleaned
