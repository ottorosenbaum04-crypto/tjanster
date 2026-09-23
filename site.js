// Kopplar config.js till sidan. Inga cookies, ingen spårning.
// Utan Stripe-länk → förhandsbokning via förifyllt mejl (ingen betalning nu).
// Utan formulärtjänst → väntelistan skickas som förifyllt mejl.
(function () {
  var S = window.SITE || {};
  var s = S.seller || {};
  var src = new URLSearchParams(location.search).get("utm_source") || "direkt";

  var PRODUCTS = {
    upphandling_analys: "Anbudsanalys, 990 kr för första analysen (därefter 1 490 kr)",
    upphandling_bevakning: "Upphandlingsbevakning, 490 kr/mån",
    rekrytering: "Rekryteringsradarn, första månaden 490 kr (därefter 690 kr/mån)",
    bidrag: "Bidragsbevakaren, första månaden 190 kr (därefter 390 kr/mån)"
  };

  function mailto(subject, body) {
    return "mailto:" + encodeURIComponent(s.email) +
      "?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
  }

  // Köpknappar: <a data-stripe="nyckel">
  document.querySelectorAll("[data-stripe]").forEach(function (a) {
    var key = a.getAttribute("data-stripe");
    var url = (S.stripe || {})[key];
    a.style.display = "";
    if (url) {
      a.href = url;
    } else if (s.email && PRODUCTS[key]) {
      a.href = mailto("Förhandsbokning: " + PRODUCTS[key],
        "Hej!\n\nVi vill förhandsboka: " + PRODUCTS[key] + " (priser exkl. eventuell moms).\n\n" +
        "Företag:\nOrganisationsnummer:\nKontaktperson:\n\n" +
        "Vi förstår att ingen betalning sker nu och att vi får bekräfta beställningen innan tjänsten startar.\n" +
        "(källa: " + src + ")");
      a.title = "Öppnar ett förifyllt mejl. Ingen betalning nu.";
    } else {
      a.style.display = "none";
    }
  });

  // Säljarinfo i sidfoten
  var parts = [s.name, s.orgnr && "Org.nr " + s.orgnr, s.city, s.email].filter(Boolean);
  document.querySelectorAll("[data-seller]").forEach(function (el) {
    el.textContent = parts.length ? parts.join(" · ") : "[Säljaruppgifter fylls i före publicering]";
  });

  // Väntelista. Källan (utm_source) sparas i dolt fält så kanaler kan mätas utan cookies.
  document.querySelectorAll("form[data-waitlist]").forEach(function (f) {
    var hidden = f.querySelector("input[name=kalla]");
    if (hidden) hidden.value = src;
    var msg = f.querySelector(".form-msg");
    f.addEventListener("submit", function (e) {
      e.preventDefault();

      if (!S.formEndpoint) {
        if (!s.email) {
          msg.textContent = "Väntelistan öppnar snart. Formuläret är inte aktiverat ännu.";
          return;
        }
        var lines = [];
        new FormData(f).forEach(function (v, k) {
          if (k === "samtycke") v = "ja";
          lines.push(k + ": " + v);
        });
        window.location.href = mailto("Väntelista: " + (f.nisch ? f.nisch.value : ""),
          "Jag vill stå på väntelistan.\n\n" + lines.join("\n"));
        msg.textContent = "Ditt e-postprogram öppnas med en färdig anmälan. Skicka mejlet för att ställa dig på listan.";
        return;
      }

      var btn = f.querySelector("button");
      btn.disabled = true;
      fetch(S.formEndpoint, { method: "POST", body: new FormData(f), headers: { Accept: "application/json" } })
        .then(function (r) {
          if (!r.ok) throw new Error();
          f.reset();
          msg.textContent = "Tack! Du står på väntelistan. Vi hör av oss före lansering.";
        })
        .catch(function () {
          msg.textContent = "Något gick fel. Försök igen eller mejla oss.";
        })
        .finally(function () { btn.disabled = false; });
    });
  });
})();
