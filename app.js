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

async function loadMatches() {
  try {
    const res = await fetch("./matches.json", { cache: "no-store" });
    const json = await res.json();
    matches = json.items || [];
    if (document.getElementById("msg")) {
      document.getElementById("msg").style.display = "block";
      document.getElementById("msg").textContent = `Données chargées : ${matches.length} match(s)`;
    }
  } catch (e) {
    showMsg("Impossible de charger matches.json (réseau/cache).");
    matches = [];
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

  const filtered = matches
    .filter(m => (level === "ALL" ? true : m.level === level))
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

async function boot() {
  $("count").textContent = "Initialisation…";

  const ok = initMap();
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


