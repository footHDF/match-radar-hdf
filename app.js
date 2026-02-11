const $ = (id) => document.getElementById(id);

function showMsg(txt) {
  const el = $("msg");
  if (!el) return;
  el.style.display = "block";
  el.textContent = txt;
}

function distanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (x) => x * Math.PI / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat/2) * Math.sin(dLat/2) +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
    Math.sin(dLon/2) * Math.sin(dLon/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

function fmtDate(iso) {
  const d = new Date(iso);
  return d.toLocaleString("fr-FR", {
    weekday:"short", day:"2-digit", month:"2-digit",
    hour:"2-digit", minute:"2-digit"
  });
}

let matches = [];

function ym(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

async function loadMatchesForMonth(ymStr) {
  try {
    // ex: ./data/2026-02.json
    const res = await fetch(`./data/${ymStr}.json`, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const json = await res.json();
    matches = json.items || [];
    showMsg(`Données chargées : ${matches.length} match(s) (${ymStr})`);
  } catch (e) {
    matches = [];
    showMsg(`Impossible de charger ./data/${ymStr}.json (fichier manquant ?)`);
  }
}


let map, userMarker;
let matchMarkers = [];
let userPos = { lat: 49.8489, lon: 3.2876 }; // Saint-Quentin par défaut


function initMap() {
  if (typeof L === "undefined") {
    showMsg("Leaflet non chargé (L undefined). Vérifie lib/leaflet.js et lib/leaflet.css.");
    return false;
  }

  const mapDiv = $("map");
  if (!mapDiv) {
    showMsg("Erreur : la zone carte (#map) est introuvable dans index.html.");
    return false;
  }

  map = L.map("map").setView([userPos.lat, userPos.lon], 9);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);

  userMarker = L.marker([userPos.lat, userPos.lon]).addTo(map).bindPopup("Vous êtes ici");
  return true;
}

function clearMatchMarkers() {
  matchMarkers.forEach(m => map.removeLayer(m));
  matchMarkers = [];
}

function render() {
  const level = $("level") ? $("level").value : "ALL";
  const radiusKm = $("radius") ? Number($("radius").value) : 25;

  clearMatchMarkers();

    const { start: wStart, end: wEnd } = getSelectedWeekendWindow();

  const filtered = matches
    .filter(m => {
      // niveau
      if (level !== "ALL" && m.level !== level) return false;

      // week-end (samedi/dimanche)
      const dt = new Date(m.starts_at);
      if (!(dt >= wStart && dt <= wEnd)) return false;

      return true;
    })
    .map(m => ({
      ...m,
      distance_m: distanceMeters(userPos.lat, userPos.lon, m.venue.lat, m.venue.lon)
    }))
    .filter(m => m.distance_m <= radiusKm * 1000)
    .sort((a,b) => new Date(a.starts_at) - new Date(b.starts_at));

  $("count").textContent = `${filtered.length} match(s) trouvé(s)`;

  const list = $("list");
  list.innerHTML = "";

  filtered.forEach(m => {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `
      <div class="meta">${m.level} • ${fmtDate(m.starts_at)} • ${(m.distance_m/1000).toFixed(1)} km</div>
      <div class="title">${m.home_team} — ${m.away_team}</div>
      <div class="place">${m.venue.name} • ${m.venue.city}</div>
      <div class="btns">
        <a class="btn" target="_blank" rel="noreferrer"
          href="https://www.google.com/maps/dir/?api=1&destination=${m.venue.lat},${m.venue.lon}">
          Itinéraire
        </a>
        ${m.source_url ? `<a class="btn" target="_blank" rel="noreferrer" href="${m.source_url}">Source</a>` : ""}
      </div>
    `;
    card.onclick = () => map.setView([m.venue.lat, m.venue.lon], 12);
    list.appendChild(card);

    const marker = L.marker([m.venue.lat, m.venue.lon])
      .addTo(map)
      .bindPopup(`<b>${m.level} • ${fmtDate(m.starts_at)}</b><br>${m.home_team} — ${m.away_team}<br>${m.venue.name} • ${m.venue.city}`);
    matchMarkers.push(marker);
  });
}

function startOfDay(d) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function addDays(d, n) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}

function startOfWeekend(d) {
  // samedi 00:00 (en heure locale)
  const x = startOfDay(d);
  const wd = x.getDay(); // 0 dim, 6 sam
  const daysToSat = (6 - wd + 7) % 7;
  return addDays(x, daysToSat);
}

function endOfWeekend(sat) {
  // dimanche 23:59:59.999
  const sun = addDays(sat, 1);
  sun.setHours(23, 59, 59, 999);
  return sun;
}

function fmtDateFR(d) {
  return d.toLocaleDateString("fr-FR", { weekday: "short", day: "2-digit", month: "short", year: "numeric" });
}

function buildMonthOptions() {
  const monthSel = document.getElementById("month");
  if (!monthSel) return;

  monthSel.innerHTML = "";

  // On propose : mois courant + 6 mois
  const now = new Date();
  const base = new Date(now.getFullYear(), now.getMonth(), 1);

  for (let i = 0; i < 7; i++) {
    const d = new Date(base.getFullYear(), base.getMonth() + i, 1);
    const id = ym(d); // YYYY-MM
    const label = d.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = label.charAt(0).toUpperCase() + label.slice(1);
    monthSel.appendChild(opt);
  }

  // par défaut : mois courant
  monthSel.value = ym(now);
}

function buildWeekendOptionsForSelectedMonth() {
  const monthSel = document.getElementById("month");
  const weekendSel = document.getElementById("weekend");
  if (!monthSel || !weekendSel) return;

  weekendSel.innerHTML = "";

  const [Y, M] = monthSel.value.split("-").map(Number);
  const monthStart = new Date(Y, M - 1, 1);
  const monthEnd = new Date(Y, M, 0); // dernier jour du mois

  // premier samedi qui tombe dans le mois (ou juste avant mais qui chevauche)
  let sat = startOfWeekend(monthStart);

  // si le samedi calculé est après la fin du mois, on recule d'une semaine (rare)
  if (sat > monthEnd) sat = addDays(sat, -7);

  // On parcourt les samedis jusqu'à dépasser le mois
  while (sat <= monthEnd) {
    const sun = addDays(sat, 1);
    const label = `Week-end du ${fmtDateFR(sat)} → ${fmtDateFR(sun)}`;
    const opt = document.createElement("option");
    opt.value = sat.toISOString(); // on stocke le samedi
    opt.textContent = label;
    weekendSel.appendChild(opt);
    sat = addDays(sat, 7);
  }

  // par défaut : prochain week-end
  const nextSat = startOfWeekend(new Date());
  weekendSel.value = nextSat.toISOString();
}

function getSelectedWeekendWindow() {
  const weekendSel = document.getElementById("weekend");
  if (!weekendSel || !weekendSel.value) {
    const sat = startOfWeekend(new Date());
    return { start: sat, end: endOfWeekend(sat) };
  }
  const sat = new Date(weekendSel.value);
  return { start: sat, end: endOfWeekend(sat) };
}



async function boot() {
  $("count").textContent = "Initialisation…";

  const ok = initMap();
    buildMonthOptions();
  buildWeekendOptionsForSelectedMonth();

  // charge le mois sélectionné
  await loadMatchesForMonth(document.getElementById("month").value);
  document.getElementById("month").addEventListener("change", async () => {
    buildWeekendOptionsForSelectedMonth();
    await loadMatchesForMonth(document.getElementById("month").value);
    render();
  });

  document.getElementById("weekend").addEventListener("change", render);
  $("level").addEventListener("change", render);
  $("radius").addEventListener("change", render);

  if (!ok) return;

  // ✅ Affiche immédiatement avec la position par défaut (Saint-Quentin)
    await loadMatches();

  render();

  // ⏱️ Sécurité : si la géolocalisation ne répond pas, on garde Lille
  let geoFinished = false;
  setTimeout(() => {
    if (!geoFinished) {
      showMsg("Géolocalisation trop lente ou bloquée : affichage de Saint-Quentin (par défaut).");
      // render() déjà fait, donc rien à faire de plus
    }
  }, 3000);

  // géolocalisation (optionnelle)
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (p) => {
        geoFinished = true;
        userPos = { lat: p.coords.latitude, lon: p.coords.longitude };
        map.setView([userPos.lat, userPos.lon], 9);
        userMarker.setLatLng([userPos.lat, userPos.lon]);
        render(); // ✅ recalcul avec ta vraie position
      },
      () => {
        geoFinished = true;
        showMsg("Position refusée : j'utilise Saint-Quentin par défaut.");
        // render() déjà fait
      },
      { enableHighAccuracy: true, timeout: 3000, maximumAge: 60000 }
    );
  } else {
    showMsg("Géolocalisation indisponible : j'utilise Saint-Quentin par défaut.");
    // render() déjà fait
  }

  $("level").addEventListener("change", render);
  $("radius").addEventListener("change", render);
}


window.addEventListener("load", boot);




