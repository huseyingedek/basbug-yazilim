// Başbuğ E-Mutabakat — karar ekranı etkileşimleri
(function () {
    "use strict";

    var form = document.getElementById("cevapForm");
    if (!form) return;

    var kararInput = document.getElementById("kararInput");
    var stepBaslangic = document.getElementById("step-baslangic");
    var stepMutabikAsk = document.getElementById("step-mutabik-ask");
    var stepForm = document.getElementById("step-form");

    var formHead = document.getElementById("formPanelHead");
    var formAsk = document.getElementById("formPanelAsk");
    var mesajLabel = document.getElementById("mesajLabel");
    var mesajField = document.getElementById("id_mesaj");
    var mesajClientErr = document.getElementById("mesajClientErr");
    var finalSubmit = document.getElementById("finalSubmit");

    function show(el) { if (el) el.hidden = false; }
    function hide(el) { if (el) el.hidden = true; }

    function reset() {
        show(stepBaslangic);
        hide(stepMutabikAsk);
        hide(stepForm);
        if (mesajClientErr) mesajClientErr.hidden = true;
    }

    function openMutabikAsk() {
        hide(stepBaslangic);
        show(stepMutabikAsk);
        hide(stepForm);
    }

    function openForm(karar) {
        kararInput.value = karar;
        hide(stepBaslangic);
        hide(stepMutabikAsk);
        show(stepForm);

        if (karar === "itiraz") {
            formHead.textContent = "✕ Mutabık Değiliz";
            formHead.className = "panel-head panel-head--no";
            formAsk.textContent = "Lütfen mutabık olmama nedeninizi belirtiniz.";
            mesajLabel.innerHTML = 'Açıklama <span class="req">*</span>';
            finalSubmit.className = "btn btn-reject btn-block";
        } else {
            formHead.textContent = "✓ Mutabıkız";
            formHead.className = "panel-head panel-head--ok";
            formAsk.textContent = "Dilerseniz bir mesaj ve dosya ekleyebilirsiniz.";
            mesajLabel.textContent = "Mesaj (tercihen)";
            finalSubmit.className = "btn btn-approve btn-block";
        }
    }

    document.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action]");
        if (!btn) return;
        var action = btn.getAttribute("data-action");

        if (action === "mutabik-ask") {
            openMutabikAsk();
        } else if (action === "itiraz") {
            openForm("itiraz");
        } else if (action === "mutabik-extra") {
            openForm("mutabik");
        } else if (action === "mutabik-gonder") {
            kararInput.value = "mutabik";
            form.submit();
        } else if (action === "geri") {
            reset();
        }
    });

    form.addEventListener("submit", function (e) {
        // İtirazda açıklama zorunlu (istemci tarafı kontrol)
        if (kararInput.value === "itiraz") {
            var val = (mesajField && mesajField.value ? mesajField.value : "").trim();
            if (!val) {
                e.preventDefault();
                if (mesajClientErr) mesajClientErr.hidden = false;
                if (mesajField) mesajField.focus();
            }
        }
    });
})();
