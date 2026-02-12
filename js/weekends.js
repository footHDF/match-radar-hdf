function weekendIdFromDate(d) {
  const day = d.getDay(); // 0=dim, 6=sam
  const offsetToSat = (6 - day + 7) % 7;
  const sat = new Date(d);
  sat.setDate(d.getDate() + offsetToSat);
  sat.setHours(0,0,0,0);
  const y = sat.getFullYear();
  const m = String(sat.getMonth()+1).padStart(2,'0');
  const da = String(sat.getDate()).padStart(2,'0');
  return `${y}-${m}-${da}`;
}

function labelWeekend(id) {
  const [y,m,d] = id.split('-').map(Number);
  const sat = new Date(y, m-1, d);
  const sun = new Date(y, m-1, d+1);
  const fmt = new Intl.DateTimeFormat('fr-FR', { day: '2-digit', month: 'short' });
  return `${fmt.format(sat)}–${fmt.format(sun)} ${y}`;
}

