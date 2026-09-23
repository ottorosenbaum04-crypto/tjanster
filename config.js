// ===== FYLL I INNAN PUBLICERING =====
// Stripe Payment Links skapas i Stripe Dashboard → Payment Links (ett per erbjudande).
// Formulär: POST-endpoint från en formulärtjänst som lagrar data inom EU.
// MINIMUM för att gå live: fyll i seller.name, seller.email och seller.city.
// Tom Stripe-länk → knappen öppnar ett förifyllt beställningsmejl (faktura efter leverans).
// Tom formEndpoint → väntelistan skickas som förifyllt mejl till seller.email.
window.SITE = {
  seller: {
    name: "Otto Rosenbaum", // t.ex. "Förnamn Efternamn (enskild firma)"
    orgnr: "",         // lämna tomt tills firman är registrerad
    email: "ottorosenbaum04@gmail.com", // kontaktadress
    city: "Uppsala"    // ort
  },
  formEndpoint: "",    // t.ex. https://<formulärtjänst>/f/abc123
  stripe: {
    upphandling_analys: "",   // Anbudsanalys, förbeställning 990 kr
    upphandling_bevakning: "",// Bevakning, 490 kr/mån
    rekrytering: "",          // Första månaden 490 kr, därefter 690 kr/mån
    bidrag: ""                // Första månaden 190 kr, därefter 390 kr/mån
  }
};
