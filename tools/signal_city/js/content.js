/* SetuCity: everything the learner reads.
   SCENES   guided walk-throughs tied to a spot in the city (use cases and concepts); also reused as lessons.
   INFO     single-card hotspots.
   PATHS    the seven study paths: ordered lessons and an end-of-path quiz.
   ART      small diagrams shown inside cards.
   A slide: { h, t, cam, fx, cut, xray, follow, labels: [[target, text, colour]], art }.
   cam: { at: place, d: distance, az: degrees round from south, el: degrees up, dy: lift }. */
(function () {
  "use strict";
  const SC = (window.SC = window.SC || {});
  const cam = (at, d, az, el, dy) => ({ at, d, az: az || 0, el: el === undefined ? 30 : el, dy: dy || 0 });
  const A = "#ffb224", B = "#37d5ff", G = "#3ddc97", P = "#a78bfa", K = "#ff6b9a";

  /* ================================================================= diagrams */
  const svg = (w, h, body) => '<svg viewBox="0 0 ' + w + " " + h + '" xmlns="http://www.w3.org/2000/svg" font-family="Outfit, Inter, sans-serif">' + body + "</svg>";
  const tx = (x, y, s, t, c, a, wt) => '<text x="' + x + '" y="' + y + '" font-size="' + s + '" fill="' + (c || "#e8eef8") + '" text-anchor="' + (a || "middle") + '" font-weight="' + (wt || 500) + '">' + t + "</text>";
  SC.ART = {
    generations: svg(420, 190, [["1G", "1980s", "Analogue voice", "#8b95a1"], ["2G", "1991", "Digital voice, SMS", B], ["3G", "2001", "Mobile data", G], ["4G", "2009", "All-IP broadband", A], ["5G", "2019", "Speed, low delay, scale", K]].map((g, i) =>
      '<rect x="' + (10 + i * 82) + '" y="' + (120 - i * 22) + '" width="72" height="' + (40 + i * 22) + '" rx="8" fill="' + g[3] + '" opacity=".9"/>' + tx(46 + i * 82, 148 - i * 22, 22, g[0], "#0b1020", "middle", 800) + tx(46 + i * 82, 176, 11, g[1], "#aab6cc") + tx(46 + i * 82, 112 - i * 22, 9.5, g[2], "#e8eef8")).join("") + tx(210, 16, 12, "Each generation, roughly ten years apart", "#aab6cc")),
    spectrum: svg(420, 190, '<defs><linearGradient id="sg" x1="0" x2="1"><stop offset="0" stop-color="' + K + '"/><stop offset=".5" stop-color="' + A + '"/><stop offset="1" stop-color="' + B + '"/></linearGradient></defs><rect x="20" y="78" width="380" height="22" rx="11" fill="url(#sg)"/>' +
      tx(60, 70, 13, "Low band", K, "middle", 700) + tx(210, 70, 13, "Mid band", A, "middle", 700) + tx(360, 70, 13, "High band", B, "middle", 700) + tx(60, 118, 11, "below 1 GHz") + tx(210, 118, 11, "1 to 6 GHz") + tx(360, 118, 11, "24 GHz and up") +
      tx(20, 150, 11.5, "Reach", "#aab6cc", "start") + '<path d="M70 146 H390" stroke="#aab6cc" stroke-width="2"/><path d="M70 146 l10 -5 v10z" fill="#aab6cc"/>' + tx(398, 150, 0, "") +
      tx(20, 176, 11.5, "Capacity", "#aab6cc", "start") + '<path d="M80 172 H400" stroke="#aab6cc" stroke-width="2"/><path d="M400 172 l-10 -5 v10z" fill="#aab6cc"/>' + tx(210, 24, 12, "Lower frequencies travel further; higher ones carry more", "#aab6cc") +
      tx(210, 42, 10.5, "Reach grows to the left, capacity grows to the right", "#7f8ca3")),
    packet: svg(420, 170, tx(210, 18, 12, "One packet: an envelope with an address on it", "#aab6cc") +
      '<rect x="14" y="40" width="150" height="74" rx="10" fill="' + B + '"/><rect x="170" y="40" width="236" height="74" rx="10" fill="' + A + '"/>' + tx(89, 66, 14, "Header", "#0b1020", "middle", 800) + tx(89, 86, 10.5, "from 10.45.0.7", "#0b1020") + tx(89, 101, 10.5, "to 142.250.4.14", "#0b1020") +
      tx(288, 72, 14, "Payload", "#0b1020", "middle", 800) + tx(288, 92, 10.5, "up to about 1,500 bytes of your data", "#0b1020") + tx(89, 134, 11, "who it is for") + tx(288, 134, 11, "a slice of the photo, page or call") + tx(210, 160, 10.5, "A single photo is cut into thousands of these", "#7f8ca3")),
    pillars: svg(420, 200, '<path d="M210 26 L384 170 H36 Z" fill="none" stroke="#3a4a6b" stroke-width="2"/>' +
      '<circle cx="210" cy="30" r="22" fill="' + P + '"/><circle cx="46" cy="166" r="22" fill="' + A + '"/><circle cx="374" cy="166" r="22" fill="' + G + '"/>' + tx(210, 35, 11, "eMBB", "#0b1020", "middle", 800) + tx(46, 170, 9.5, "URLLC", "#0b1020", "middle", 800) + tx(374, 170, 10, "mMTC", "#0b1020", "middle", 800) +
      tx(210, 70, 11.5, "Enhanced mobile broadband") + tx(210, 85, 10.5, "gigabit video, AR, fixed wireless", "#aab6cc") + tx(84, 150, 10.5, "Ultra-reliable,", "#e8eef8", "start") + tx(84, 164, 10.5, "low-latency: robots, cars", "#aab6cc", "start") + tx(336, 150, 10.5, "Massive machine-type:", "#e8eef8", "end") + tx(336, 164, 10.5, "a million sensors per km²", "#aab6cc", "end")),
    handover: svg(420, 180, tx(210, 16, 12, "Signal strength as you drive from cell A to cell B", "#aab6cc") + '<path d="M30 150 H400 M30 150 V30" stroke="#3a4a6b" stroke-width="2"/>' +
      '<path d="M30 48 C150 54 250 110 400 140" fill="none" stroke="' + B + '" stroke-width="3"/><path d="M30 140 C170 120 260 60 400 46" fill="none" stroke="' + A + '" stroke-width="3"/>' + tx(60, 42, 11, "cell A", B) + tx(372, 38, 11, "cell B", A) +
      '<path d="M252 30 V150" stroke="' + G + '" stroke-width="2" stroke-dasharray="5 4"/>' + tx(252, 168, 11, "handover", G, "middle", 700) + '<path d="M213 30 V150" stroke="#7f8ca3" stroke-width="1" stroke-dasharray="2 4"/>' + tx(190, 168, 9.5, "curves cross", "#7f8ca3") + tx(330, 100, 10, "wait until B is clearly", "#aab6cc") + tx(330, 113, 10, "better, to avoid ping-pong", "#aab6cc")),
    latency: svg(420, 170, tx(210, 16, 12, "Round-trip delay, typical", "#aab6cc") + [["4G to a distant cloud", 300, "50 ms", "#8b95a1"], ["5G to a distant cloud", 190, "30 ms", A], ["5G to a city edge node", 62, "8 ms", B], ["5G on-site private core", 26, "2 to 5 ms", G]].map((r, i) =>
      tx(14, 46 + i * 34, 11, r[0], "#e8eef8", "start") + '<rect x="14" y="' + (52 + i * 34) + '" width="' + r[1] + '" height="12" rx="6" fill="' + r[3] + '"/>' + tx(24 + r[1], 62 + i * 34, 11, r[2], r[3], "start", 700)).join("")),
    split: svg(420, 170, [["RU", "Radio unit", "at the antenna", G, 14], ["DU", "Distributed unit", "real-time: scheduling", B, 152], ["CU", "Central unit", "RRC, PDCP, mobility", P, 290]].map((b) =>
      '<rect x="' + b[4] + '" y="44" width="116" height="78" rx="12" fill="' + b[3] + '"/>' + tx(b[4] + 58, 76, 22, b[0], "#0b1020", "middle", 800) + tx(b[4] + 58, 95, 10.5, b[1], "#0b1020", "middle", 700) + tx(b[4] + 58, 110, 9.5, b[2], "#0b1020")).join("") +
      '<path d="M130 83 H152 M268 83 H290" stroke="#e8eef8" stroke-width="3"/>' + tx(141, 74, 9.5, "fronthaul", "#aab6cc") + tx(279, 74, 9.5, "midhaul", "#aab6cc") + tx(210, 22, 12, "A 5G base station (gNB) can be split into three parts", "#aab6cc") + tx(210, 150, 10.5, "then backhaul carries everything on to the core", "#7f8ca3")),
    heatkey: svg(420, 110, tx(210, 18, 12, "Reference signal strength (RSRP) at street level", "#aab6cc") + [["#22c55e", "Excellent"], ["#a3e635", "Good"], ["#facc15", "Fair"], ["#fb923c", "Weak"], ["#ef4444", "Poor"]].map((c, i) =>
      '<path transform="translate(' + (50 + i * 80) + ' 58)" d="M-22 0 L-11 -19 H11 L22 0 L11 19 H-11Z" fill="' + c[0] + '"/>' + tx(50 + i * 80, 98, 11, c[1])).join("")),
    session: svg(420, 190, tx(210, 16, 12, "Getting online, in order", "#aab6cc") + [["1", "Find a cell and connect by radio (RRC)", G], ["2", "Register: AMF checks who you are (AUSF, UDM)", B], ["3", "Ask for a PDU session: SMF picks a UPF", B], ["4", "Phone gets an IP address and a QoS flow", A], ["5", "Data flows: phone, gNB, UPF, internet", A]].map((s, i) =>
      '<circle cx="28" cy="' + (44 + i * 30) + '" r="11" fill="' + s[2] + '"/>' + tx(28, 48 + i * 30, 12, s[0], "#0b1020", "middle", 800) + tx(50, 48 + i * 30, 12, s[1], "#e8eef8", "start")).join("") + '<path d="M28 55 V153" stroke="#3a4a6b" stroke-width="2" stroke-dasharray="2 5"/>'),
  };

  /* ================================================================= scenes: use cases and concepts */
  const overview = cam("city", 540, 30, 38);
  SC.OVERVIEW = overview;
  SC.SCENES = {
    /* ---------------- use cases */
    av: {
      kind: "usecase", title: "Autonomous Vehicles", place: "av", dy: 9, blurb: "How self-driving cars lean on a fast, dependable network, and what they say to each other.",
      slides: [
        { h: "A car that is never out of touch", t: "The white car with the blue stripe drives itself. Its own cameras and radar do the steering, but the network extends what it can see: hazards round a corner, a red light two junctions ahead, a road closure across town.", cam: cam("av", 70, 25, 28), follow: "avCar", fx: ["v2x"], labels: [["avCar", "Autonomous vehicle", B]] },
        { h: "Vehicle-to-everything (V2X)", t: "Cars exchange short safety messages with each other (V2V), with roadside units on lamp posts (V2I) and with the wider network (V2N). The blue lines are car-to-car links; the lime ones reach the nearest roadside small cell.", cam: cam("av", 120, -20, 42), follow: "avCar", fx: ["v2x", "smallcells"], labels: [["avCar", "Autonomous vehicle", B]] },
        { h: "Why latency matters", t: "At 50 km/h a car covers about 14 m every second. A 100 ms delay means 1.4 m travelled before a warning even arrives. 5G's ultra-reliable low-latency mode aims for a few milliseconds, and 99.999% delivery.", cam: cam("av", 60, 60, 20), follow: "avCar", fx: ["v2x"], art: "latency" },
        { h: "Never dropping the link", t: "As the car moves it is handed from cell to cell. Watch the thick line: it switches to the next cell site only once that site is clearly stronger. Edge servers near the road keep map and traffic data close.", cam: cam("city", 400, 10, 48), fx: ["handover"], labels: [["hoCar", "Moving car", A]] },
      ],
    },
    factory: {
      kind: "usecase", title: "Smart Factory", place: "factory", dy: 16, blurb: "Wireless robots, moving parts carriers and a production line you can rearrange overnight.",
      pins: [
        { at: "factory.arm", h: "Robotic production line", t: "5G can replace the fixed industrial cabling between controllers and robot arms. With the cables gone, a line can be physically rearranged for a new product in hours instead of weeks." },
        { at: "factory.agv", h: "Automated guided vehicles", t: "These carriers receive routes and report position many times a second. They need coverage in every aisle and a seamless handover between indoor radios; Wi-Fi roaming gaps are a common reason factories look at 5G." },
        { at: "factory.radio", h: "Indoor radio unit", t: "A small ceiling-mounted radio gives the hall its own dedicated 5G cell. Several are usually spread around so metal machinery does not shadow any workstation." },
      ],
      slides: [
        { h: "Lift the roof", t: "Inside this plant five robot arms work a conveyor while carriers shuttle parts. Every one of them is on the factory's own 5G network instead of a cable.", cam: cam("factory", 74, 18, 44), cut: ["factory"], fx: ["factoryNet"] },
        { h: "Control loops over the air", t: "A robot controller sends a command, the arm answers with its position, thousands of times a minute. If a message is late the arm must stop. That is why factories ask for delays of a few milliseconds and near-perfect reliability.", cam: cam("factory.arm", 30, -25, 34), cut: ["factory"], fx: ["factoryNet"] },
        { h: "Keep the data on site", t: "The processing sits in an edge node at the kerb, not a cloud region hundreds of kilometres away. The green path is the short loop to the edge; the red one is the long trip it replaces.", cam: cam("factory", 150, 40, 34), fx: ["edge"], art: "latency" },
      ],
    },
    health: {
      kind: "usecase", title: "5G for Healthcare", place: "hospital", dy: 16, blurb: "A connected ward and an operating theatre where the surgeon may be in another city.",
      pins: [
        { at: "ward.theatre", h: "Remote surgery", t: "The robotic arm follows a surgeon's hand movements sent over the network, and returns video and touch feedback. The round trip must stay under roughly 10 ms to feel natural, which calls for a guaranteed low-latency slice." },
        { at: "ward.beds", h: "Wireless patient monitoring", t: "Bedside monitors report heart rate, oxygen and temperature continuously. Each sends little data, but there are hundreds of them and none may be silently lost." },
        { at: "ward.console", h: "Specialist video console", t: "High-resolution scans and live 4K video are shared with specialists elsewhere. This is the broadband side of 5G: lots of data, where a short delay is tolerable." },
        { at: "helipad", h: "Connected ambulance", t: "An ambulance or air ambulance can stream vital signs and video ahead, so the emergency team is briefed before the patient arrives." },
      ],
      slides: [
        { h: "Inside the hospital", t: "The top floor has been opened up. On the left, a ward of monitored beds. On the right, an operating theatre with a robotic arm.", cam: cam("ward", 50, 20, 50), cut: ["hospital"], fx: ["ward"] },
        { h: "Three needs, one building", t: "Sensors need many cheap connections. Scans and video need raw capacity. The surgical robot needs speed and certainty. 5G can serve all three at once by giving each its own slice of the network.", cam: cam("ward.theatre", 26, -30, 40), cut: ["hospital"], fx: ["ward"], art: "pillars" },
      ],
    },
    port: {
      kind: "usecase", title: "Connected Port", place: "port", dy: 30, blurb: "A private 5G network covering a kilometre of quayside, cranes and ships.",
      pins: [
        { at: "portmast", h: "Wide-area coverage", t: "Unlike Wi-Fi, a single private 5G mast can cover the whole expanse of ground a port is built on, so people and machines stay connected wherever they are on site." },
        { at: "port.crane", h: "Remote-controlled cranes", t: "Operators drive these cranes from a control room using live video. One operator can supervise several cranes, and nobody has to climb 30 m in bad weather." },
        { at: "port.core", h: "On-site core", t: "The port runs its own small core network in this cabinet. Traffic never leaves the site, which keeps delay low and operations data private." },
        { at: "port.ship", h: "Ship alongside", t: "While berthed, a vessel can join the port network to exchange manifests, engine telemetry and crew traffic." },
      ],
      slides: [
        { h: "A network of its own", t: "The purple dome marks a private 5G network: radio, spectrum and core dedicated to this one site. Public phones outside cannot use it, and the port's devices get all of its capacity.", cam: cam("port", 210, -62, 32), fx: ["private"] },
        { h: "Machines first", t: "Cranes, straddle carriers and sensors on every container report continuously. Uplink video from the cranes dominates, the reverse of a normal consumer network where downloads do.", cam: cam("port.crane", 90, -110, 22), fx: ["private"], labels: [["portmast", "Private 5G mast", P]] },
      ],
    },
    farm: {
      kind: "usecase", title: "Smart Farming", place: "farm.harvester", dy: 8, blurb: "Soil sensors, livestock tags and a harvester with nobody in the cab.",
      pins: [
        { at: "farm.harvester", h: "Automated machinery", t: "Connected machinery such as this autonomous harvester follows centimetre-accurate paths and reports yield as it goes, easing the workload at the busiest time of year." },
        { at: "farm.sensor", h: "Soil and weather sensors", t: "Each pole measures moisture and temperature and reports a few bytes every few minutes. Low-power modes such as NB-IoT let one battery last around ten years." },
        { at: "farm.barn", h: "Livestock monitoring", t: "Tags on animals report location and health indicators, flagging illness days before it is visible." },
      ],
      slides: [
        { h: "Coverage where few people live", t: "Farms are large and sparsely populated, so they depend on tall, low-band macro sites like the one at the field edge. The green links are sensors reporting in; the amber one is the harvester.", cam: cam("farm", 150, 70, 34), fx: ["farm"], labels: [["harvester", "Autonomous harvester", A], ["easttower", "Rural macro site", B]] },
        { h: "Many small voices", t: "This is massive machine-type communication: thousands of devices, each saying very little. The network's job is to hear all of them while letting them sleep most of the time.", cam: cam("farm.harvester", 46, 110, 24), follow: "harvester", fx: ["farm", "iot"] },
      ],
    },
    drone: {
      kind: "usecase", title: "Aerial Drones", place: "dronepad", dy: 30, blurb: "Drones controlled over 5G, and drones that carry 5G to where it is missing.",
      slides: [
        { h: "Beyond line of sight", t: "A hobby drone is flown by a handheld radio and must stay in view. Over 5G, a controller can command a drone anywhere the network reaches, with live video coming back.", cam: cam("park", 120, 30, 30, 20), follow: "drone", fx: ["drone"], labels: [["drone", "Delivery drone", G]] },
        { h: "A flying cell site", t: "The idea also works in reverse. A drone or tethered balloon can carry a small base station to cover a disaster area, a festival or a network outage. The green cone is the patch of ground it could serve.", cam: cam("park", 150, -30, 46, 10), follow: "drone", fx: ["drone", "cells"] },
      ],
    },
    fwa: {
      kind: "usecase", title: "5G Home Broadband (FWA)", place: "home", dy: 12, blurb: "Fixed wireless access: fibre-like broadband with no cable to the house.",
      pins: [
        { at: "home.cpe", h: "Outdoor receiver", t: "A small antenna unit on the gable points at the nearest 5G site. Mounted outside and up high, it gets a far stronger signal than a phone indoors would." },
        { at: "home.router", h: "Indoor router", t: "The receiver feeds a normal Wi-Fi router. Laptops and TVs see ordinary Wi-Fi and never know the link to the outside world is cellular." },
        { at: "home.tv", h: "What it is used for", t: "Streaming, video calls, gaming, home working. A household uses far more data than a phone, so fixed wireless leans on wide mid-band or mmWave channels." },
      ],
      slides: [
        { h: "Broadband without digging", t: "Laying fibre to every home is slow and costly. Fixed wireless access covers the last few hundred metres by radio instead: a beam from the cell site to a receiver on the house.", cam: cam("home", 46, 28, 36), cut: ["home"], fx: ["fwa"] },
        { h: "From tower to television", t: "Follow the chain: cell site, outdoor receiver, cable down the wall, Wi-Fi router, your devices. The operator connects a street in days, not months.", cam: cam("home", 170, -40, 30), fx: ["fwa", "waves"], labels: [["southtower", "Serving cell site", B]] },
      ],
    },
    stadium: {
      kind: "usecase", title: "Stadiums and Crowds", place: "stadium", dy: 20, blurb: "Sixty thousand phones in one bowl, all uploading the same goal.",
      slides: [
        { h: "The hardest place to cover", t: "A full stadium packs more devices into a hectare than a city centre does in a square kilometre. One big cell would be shared so thinly that nobody could send a message.", cam: cam("stadium", 90, 30, 36), fx: ["stadium"] },
        { h: "Slice the crowd into many cells", t: "The answer is many narrow beams, each serving one block of seats, from antennas on the floodlight masts and under the roof. Every beam reuses the same frequencies without touching its neighbour.", cam: cam("stadium", 70, -60, 50), fx: ["stadium"] },
      ],
    },
    city: {
      kind: "usecase", title: "Smart City Sensors", place: "street", dy: 14, blurb: "Street lights, meters, bins and parking bays that report in on their own.",
      slides: [
        { h: "A city that reports on itself", t: "Each green spark is one small message: a street light reporting a failed lamp, a meter reading, a full bin, a free parking bay. Individually tiny, together millions a day.", cam: cam("city", 380, -30, 40), fx: ["iot"] },
        { h: "Built for scale, not speed", t: "These devices need long battery life and deep coverage, not megabits. 5G's massive IoT targets a million devices per square kilometre, using narrow channels and long sleep cycles.", cam: cam("houses", 150, 40, 38), fx: ["iot"], art: "pillars" },
      ],
    },

    /* ---------------- concepts */
    fibre: {
      kind: "concept", title: "Optical Infrastructure", place: "downtown", dy: 26, blurb: "X-ray the city to see the fibre under the streets that every cell site depends on.",
      pins: [
        { at: "rooftop", h: "Rooftop cell site", t: "Fibre climbs the riser of this tower to feed the antennas on the roof. Without that fibre the site could not carry more than a trickle of traffic." },
        { at: "hilltower.base", h: "Hilltop site", t: "Remote sites are costly to reach with fibre. Where a trench is impractical, a microwave dish links the site to the nearest fibre point instead." },
        { at: "manhole", h: "Cable landing", t: "A submarine cable comes ashore here and joins the city's ducts. Cables like it carry almost all traffic between continents." },
        { at: "coreGate", h: "Into the core", t: "Every strand ends up at the data centre, where the mobile core and the route to the internet sit." },
      ],
      slides: [
        { h: "The wireless network is mostly wires", t: "Only the last few hundred metres are radio. Switch on X-ray and the buildings fade to show the fibre ducts beneath every street, with risers climbing to rooftop antennas.", cam: cam("downtown", 250, 30, 40, -20), xray: true, fx: ["fibre"] },
        { h: "Backhaul", t: "The amber routes are backhaul: each cell site's link to the core. A busy 5G site needs 10 Gbit/s or more, which is why operators count their fibre as carefully as their spectrum.", cam: cam("city", 400, -25, 50), xray: true, fx: ["fibre"] },
        { h: "Out to the world", t: "From the data centre the traffic heads south, under the beach and out along a submarine cable. A page loaded from another continent crosses an ocean and returns in a fraction of a second.", cam: cam("landing", 220, -20, 30), xray: true, fx: ["fibre", "internet"] },
      ],
    },
    heat: {
      kind: "concept", title: "Heat Map of Coverage", place: "mall", dy: 16, blurb: "See signal strength street by street, and why some corners are weak.",
      slides: [
        { h: "Signal, street by street", t: "Each hexagon is a place you could stand, coloured by the strongest signal available there. Green is excellent; red means a call may drop. Buildings are left blank.", cam: cam("city", 360, 0, 78), fx: ["heat"], art: "heatkey" },
        { h: "Shadows cast by buildings", t: "Look behind the tall towers: amber and red patches appear where a building stands between you and the cell site. Radio at these frequencies does not pass through concrete well, it must bend or reflect round.", cam: cam("downtown", 250, 15, 62, -30), fx: ["heat"], labels: [["rooftop", "Rooftop cell site", B]] },
        { h: "Filling the gaps", t: "Small cells on lamp posts create local pools of green where the big sites cannot reach. Planning a network is largely the art of finding the red and deciding what to put there.", cam: cam("park", 130, -20, 66), fx: ["heat"], labels: [["smallcell", "Active small cell", G]] },
        { h: "This is what a digital twin computes", t: "The companion project in this repository does the same job properly: it ray-traces a real campus, building by building, to predict signal and choose the best cell and channel for every user.", cam: cam("city", 420, 40, 46), fx: ["heat", "waves"] },
      ],
    },
    smallcells: {
      kind: "concept", title: "Small Cell Connectivity", place: "smallcell", dy: 8, blurb: "Lamp-post radios that add capacity exactly where the crowds are.",
      pins: [
        { at: "smallcell", h: "A radio on a lamp post", t: "This shoebox-sized unit is a complete low-power base station. It covers 50 to 200 m, enough for a junction or a square." },
        { at: "parkUser", h: "The benefit for a user", t: "This person shares a small cell with a few dozen others instead of sharing a macro cell with thousands, so each gets far more capacity." },
      ],
      slides: [
        { h: "Big cells for reach, small cells for crowds", t: "Macro sites on towers cover wide areas. Where demand is dense, a park at lunchtime or a shopping street, operators add small cells at street level. Each green disc is one.", cam: cam("park", 130, 25, 46), fx: ["smallcells"], labels: [["smallcell", "Connected small cell", G]] },
        { h: "At street level", t: "Passing vehicles and pedestrians are picked up by whichever small cell they are nearest, and handed back to the macro layer when they leave.", cam: cam("street", 70, 80, 16), fx: ["smallcells", "beams"], labels: [["smallcell", "Connected small cell", G]] },
        { h: "A layered network", t: "Put the layers together: wide macro cells in colour underneath, small cells on top. Engineers call this a heterogeneous network, or HetNet.", cam: cam("city", 380, 20, 55), fx: ["smallcells", "cells"] },
      ],
    },
    datacentre: {
      kind: "concept", title: "Data Centre Architecture", place: "core", dy: 16, blurb: "Open the building that houses the mobile core and see what each row of racks does.",
      pins: [
        { at: "core.racks", h: "Control-plane functions", t: "These racks run the software that decides things: the AMF tracks where each phone is, the SMF sets up data sessions, the UDM holds subscriptions, the AUSF authenticates SIM cards." },
        { at: "core.upf", h: "User-plane function (UPF)", t: "The UPF is the workhorse that forwards your actual data between the radio network and the internet, counting usage and enforcing speed limits on the way." },
        { at: "core.trays", h: "Overhead cable trays", t: "Fibre from every cell site in the city arrives along these trays. Two physically separate routes are used so one cut cable cannot isolate the core." },
        { at: "core.control", h: "Operations room", t: "Engineers watch alarms and traffic for the whole network here. Most 5G core functions are now software in containers, scaled up and down automatically." },
      ],
      slides: [
        { h: "The brain of the network", t: "With the roof off you can see rows of server racks. This is the mobile core. Every call, message and web page handled by the city's cell sites passes through software running here.", cam: cam("core", 76, 22, 46), cut: ["core"], fx: ["coreFlow"] },
        { h: "Two kinds of work", t: "Control-plane racks make decisions: who are you, where are you, what are you allowed. User-plane racks move the data itself. 5G separates the two so each can grow on its own.", cam: cam("core", 52, -30, 56), cut: ["core"], fx: ["coreFlow"] },
        { h: "The same thing as a diagram", t: "Floating above the building is the 5G core as engineers draw it. Blue boxes are control functions sharing one service bus. The amber path is your data: radio site, UPF, internet.", cam: cam("core", 130, 0, 12, 22), fx: ["core"] },
      ],
    },
    office: {
      kind: "concept", title: "5G for Business", place: "biz", dy: 34, blurb: "An office floor served from the ceiling: indoor coverage and the end of the desk cable.",
      pins: [
        { at: "office.cell", h: "Indoor small cell", t: "Modern glass blocks radio almost as well as a wall. A ceiling unit on each floor brings the network inside instead of hoping the street signal gets through." },
        { at: "office.desks", h: "Wireless desks", t: "Laptops, phones and screens all connect over the air. Moving a team to another floor no longer means rewiring it." },
        { at: "office.meet", h: "Meeting spaces", t: "Video meetings are steady two-way streams. Predictable uplink matters more here than peak download speed." },
      ],
      slides: [
        { h: "Coverage starts indoors", t: "Around 80% of mobile data is used inside buildings. The top floor of this tower is opened up: one ceiling-mounted small cell serves every desk.", cam: cam("office", 50, 35, 44), cut: ["office"], fx: ["office"] },
        { h: "Fed from the riser", t: "The small cell is wired down the building's riser to a fibre in the street, the same optical network that feeds the outdoor sites.", cam: cam("biz", 150, 50, 28), cut: ["office"], fx: ["office", "backhaul"] },
      ],
    },
    slicing: {
      kind: "concept", title: "Network Slicing", place: "hq", dy: 60, blurb: "One physical network, several virtual ones, each tuned to a different job.",
      slides: [
        { h: "Three lanes on one road", t: "Leaving the rooftop site are three coloured pipes sharing the same fibre. Each is a slice: a virtual network with its own rules, running over common equipment.", cam: cam("downtown", 190, 25, 34, -20), fx: ["slices"], art: "pillars" },
        { h: "Different promises", t: "Purple carries fat, bursty video. Amber carries few but urgent control messages that must never queue. Green carries a drizzle of tiny sensor readings. The network guarantees each its own treatment.", cam: cam("core", 200, 60, 30), fx: ["slices"] },
      ],
    },
    corenet: {
      kind: "concept", title: "The 5G Core, Drawn in the Air", place: "core", dy: 40, blurb: "The functions of the core as a hologram: who talks to whom, and why.", noPin: true,
      slides: [
        { h: "Meet the functions", t: "Every box is a piece of software with one job. AMF: access and mobility. SMF: sessions. UPF: forwarding data. UDM and AUSF: who you are. PCF: policy. NRF: a directory so they can find each other.", cam: cam("core", 130, 0, 12, 22), fx: ["core"] },
        { h: "Control plane and user plane", t: "Blue functions exchange signalling over a shared service bus, using ordinary web-style APIs. Your photos and videos never touch them; they take the amber path through the UPF.", cam: cam("core", 110, 25, 16, 22), fx: ["core"], art: "session" },
      ],
    },
    satellite: {
      kind: "concept", title: "Satellites and Remote Coverage", place: "ground", dy: 14, blurb: "Non-terrestrial networks: reaching ships, farms and mountains from orbit.",
      slides: [
        { h: "Where towers cannot go", t: "Open sea, deserts and mountains will never justify a tower. A low-earth-orbit satellite a few hundred kilometres up can act as a base station in the sky, lighting a wide spot beam on the ground.", cam: cam("farm", 330, 80, 26, 60), fx: ["satellite"], labels: [["sat", "LEO satellite", P]] },
        { h: "The gateway", t: "The satellite still needs a way home. The dish on the hill is a gateway: it relays traffic between the satellite and the same core network the towers use.", cam: cam("ground", 110, 150, 16, 10), fx: ["satellite"], labels: [["ground", "Satellite gateway", A]] },
      ],
    },
    edge: {
      kind: "concept", title: "Edge Computing", place: "edge", dy: 9, blurb: "Moving the servers closer so the answer comes back sooner.",
      slides: [
        { h: "Distance is delay", t: "Signals in fibre cover about 200 km per millisecond. If the server is 1,000 km away, 10 ms is lost before any computing happens. The red path shows that long trip.", cam: cam("logistics", 190, 40, 30), fx: ["edge"], art: "latency" },
        { h: "Compute at the kerb", t: "An edge node is a small data centre placed near the users, here a container beside the warehouse. A local UPF hands traffic straight to it, so the round trip stays in the neighbourhood.", cam: cam("edge", 46, 30, 26), fx: ["edge"], labels: [["edge", "Edge node", G]] },
      ],
    },
  };

  /* ================================================================= single-card info hotspots */
  SC.INFO = [
    { id: "i-macro", place: "hilltower", dy: 8, h: "Macro cell site", t: "A tall mast with three sets of panel antennas, each covering a 120° sector. Mounted high on a hill it can serve users several kilometres away. The round dish is a microwave link to the next site.", cam: cam("hilltower", 60, 20, 12, -8), fx: ["waves"] },
    { id: "i-roof", place: "rooftop", dy: 7, h: "Rooftop site", t: "In city centres there is no room for towers, so antennas go on the tallest roofs. Height gets the signal over neighbouring buildings; the owner is paid rent for the space.", cam: cam("rooftop", 70, 30, 18, -6), fx: ["waves"] },
    { id: "i-museum", place: "museum", dy: 14, h: "Museum of Telecoms", t: "On the plinths: a 1980s brick phone, a 2G handset, a 3G camera phone, a 4G smartphone and a 5G foldable. Behind the building stands an old lattice broadcast mast.", cam: cam("museum.phones", 34, 10, 20), art: "generations" },
    { id: "i-wind", place: "wind", dy: 4, h: "Smart energy grid", t: "Wind turbines and solar farms produce power unevenly. Sensors on each unit report output second by second so the grid can balance supply and demand, a classic massive-IoT job.", cam: cam("wind", 110, 20, 14, -14) },
    { id: "i-landing", place: "landing", dy: 10, h: "Cable landing station", t: "Where a submarine cable meets the land. A single modern cable carries hundreds of terabits per second; a few hundred of them carry nearly all intercontinental internet traffic.", cam: cam("landing", 80, -30, 28), fx: ["internet"] },
    { id: "i-solar", place: "solar", dy: 8, h: "Powering the network", t: "A mobile network spends most of its electricity at the radio sites. 5G radios can sleep for microseconds between transmissions, and many sites now add solar and batteries.", cam: cam("solar", 90, 60, 30) },
    { id: "i-campus", place: "campus", dy: 20, h: "University campus", t: "Campuses are popular for 5G testbeds: a defined area, many users, and researchers on hand. The digital twin in this repository models exactly such a campus, IIT Gandhinagar.", cam: cam("campus", 90, -30, 34) },
    { id: "i-mall", place: "mall", dy: 14, h: "Indoor coverage systems", t: "Large buildings use a distributed antenna system: one base station feeding dozens of small ceiling antennas, so the signal is even from the food court to the car park.", cam: cam("mall", 80, 30, 36) },
    { id: "i-ship", place: "port.ship", dy: 12, h: "Coverage at sea", t: "Coastal cells reach perhaps 30 km offshore. Beyond that a ship relies on satellite, which is one reason 5G standards now include non-terrestrial networks.", cam: cam("port.ship", 130, -80, 20), fx: ["satellite"] },
    { id: "i-beach", place: "southtower", dy: 8, h: "Seasonal demand", t: "This site is quiet in winter and overloaded on a summer weekend. Operators plan capacity for the busiest hour, and can add temporary cells on wheels for events.", cam: cam("beach", 150, 20, 26), fx: ["cells"] },
  ];

  /* ================================================================= study paths */
  const L = (title, slides) => ({ title, slides });
  const S = (scene, title) => ({ scene, title });
  SC.PATHS = [
    {
      id: "gen", title: "The Technologies", color: A, blurb: "How mobile networks grew from 1G voice to 5G, what radio spectrum is, and why every network is built from cells.",
      lessons: [
        L("From 1G to 5G", [
          { h: "A young industry", t: "The first commercial mobile networks opened around 1980. Outside the Museum of Telecoms stand five handsets, one for each generation since.", cam: cam("museum.phones", 44, 12, 22), labels: [["museum.phones", "Five generations of handset", A]] },
          { h: "1G and 2G: voice goes mobile, then digital", t: "1G carried analogue voice and nothing else; anyone with a scanner could listen in. 2G (GSM, 1991) made calls digital and encrypted, and added the text message.", cam: cam("museum", 70, -20, 26), art: "generations" },
          { h: "3G and 4G: the internet in your pocket", t: "3G brought usable mobile data. 4G (LTE) dropped the old telephone circuits entirely: everything, including voice, became internet packets. Speeds rose from kilobits to tens of megabits.", cam: cam("museum.mast", 80, 40, 20), art: "generations" },
          { h: "5G: three goals at once", t: "5G is not only faster. It was designed for three things together: more capacity, very low delay with high reliability, and connecting huge numbers of simple devices.", cam: overview, fx: ["waves"], art: "pillars" },
        ]),
        L("Radio Waves and Spectrum", [
          { h: "Information riding on waves", t: "A cell site talks to your phone with radio waves, the same kind of energy as light but at far lower frequency. The rings show a signal spreading outward and weakening as it goes.", cam: cam("hilltower", 150, 20, 18, -10), fx: ["waves"] },
          { h: "Frequency is a trade-off", t: "Low frequencies travel far and pass through walls but carry little data. High frequencies carry enormous amounts but fade in a few hundred metres. The three rings show typical reach from one site.", cam: cam("downtown", 480, 20, 50, -30), fx: ["spectrum"], art: "spectrum" },
          { h: "A scarce, licensed resource", t: "Two transmitters on the same frequency in the same place interfere. Governments therefore license spectrum, often by auction for billions. An operator's spectrum is among its most valuable assets.", cam: cam("downtown", 380, -30, 40, -30), fx: ["spectrum"] },
        ]),
        L("Why Networks Are Cellular", [
          { h: "One big transmitter does not scale", t: "A single mast could cover the whole city, but everyone would share one set of frequencies. A few hundred calls and it would be full.", cam: cam("hilltower", 420, 10, 34, -40), fx: ["waves"] },
          { h: "Divide the map into cells", t: "Instead the area is split into cells, each with its own site. Because cells are small, the same frequencies can be reused a short distance away. More cells means more total capacity.", cam: cam("city", 440, 0, 62), fx: ["cells"] },
          { h: "Sectors", t: "Each site is usually split three ways, like slices of a pie, by pointing three antennas 120° apart. One mast becomes three cells. The shades of each colour show a site's three sectors.", cam: cam("city", 330, 40, 50), fx: ["cells", "waves"] },
        ]),
        L("Anatomy of a Cell Site", [
          { h: "Antennas", t: "The white panels near the top are the antennas, tilted slightly down toward their users. A modern 5G panel contains 64 or more small elements that work together to steer beams.", cam: cam("hilltower", 34, 25, 6, -3), labels: [["hilltower", "Panel antennas, three sectors", B]] },
          { h: "Radio and baseband", t: "Behind each antenna a radio unit turns digital samples into radio waves. In the cabinet at the base, the baseband computes what to send to whom, a thousand or more times a second.", cam: cam("hilltower.base", 30, 40, 22), labels: [["hilltower.base", "Baseband cabinet", A]] },
          { h: "Backhaul", t: "A site is useless without a link back to the core. Most use fibre; the dish on this mast is a microwave link, the usual fallback for hilltops.", cam: cam("hilltower", 300, 30, 30, -20), fx: ["backhaul"] },
        ]),
      ],
      quiz: [
        { type: "mc", q: "Which generation first carried voice as internet packets, with no telephone circuits at all?", options: ["2G", "3G", "4G", "1G"], answer: 2, why: "4G (LTE) is an all-IP network. Voice became VoLTE, just another packet stream." },
        { type: "mc", q: "A low-band signal (700 MHz) compared with mmWave (26 GHz) will…", options: ["carry more data but over a shorter range", "reach further but carry less data", "reach further and carry more data", "behave the same"], answer: 1, why: "Lower frequencies travel further and penetrate walls, but less bandwidth is available there." },
        { type: "mc", q: "Why are mobile networks divided into cells?", options: ["So frequencies can be reused, multiplying capacity", "Because masts cannot be taller than 30 m", "To make handsets cheaper", "To avoid needing a core network"], answer: 0, why: "Small cells let the same spectrum be reused again and again across the map." },
        { type: "order", q: "Put the generations in order, oldest first.", items: ["Analogue voice", "Digital voice and SMS", "First mobile data", "All-IP broadband", "Low latency and massive IoT"], why: "1G, 2G, 3G, 4G, 5G: roughly one generation a decade." },
      ],
    },
    {
      id: "online", title: "Accessing the Internet", color: B, blurb: "Follow a web page from a phone in the park, over the air, under the streets, through the core and out to the world.",
      lessons: [
        L("What Is the Internet?", [
          { h: "A network of networks", t: "The internet is not one thing owned by one company. It is tens of thousands of separate networks that agree to carry each other's traffic. Your mobile operator is one of them.", cam: cam("landing", 330, -15, 26, 20), fx: ["internet"] },
          { h: "Cables under the sea", t: "Nearly all traffic between continents travels through fibre-optic cables on the seabed. One comes ashore just south of this city.", cam: cam("internet", 190, 150, 14, -10), fx: ["internet"] },
          { h: "Where the content lives", t: "The web pages and videos you ask for sit on servers in data centres. Popular content is copied to servers near you so it does not have to cross an ocean every time.", cam: cam("core", 150, 30, 30), fx: ["internet", "backhaul"] },
        ]),
        L("What Is a Packet of Data?", [
          { h: "Meet our user", t: "Someone on a park bench taps a link. In the next fifth of a second their request will travel to a server and the page will come back. We will follow it.", cam: cam("parkUser", 34, 30, 22), labels: [["parkUser", "Our user", A]] },
          { h: "Cut into pieces", t: "Nothing is sent whole. Data is chopped into packets of up to about 1,500 bytes. Each carries the address it is going to and the address it came from, like an envelope.", cam: cam("parkUser", 60, -20, 30), fx: ["uplink"], art: "packet" },
          { h: "Every packet finds its own way", t: "Packets from the same photo may take different routes and arrive out of order. The receiving end reassembles them and asks again for any that went missing.", cam: cam("park", 210, 20, 36), fx: ["uplink", "backhaul"] },
        ]),
        L("The Radio Hop", [
          { h: "Uplink and downlink", t: "The amber dots are the uplink, phone to site; the blue ones are the downlink coming back. This is the only wireless part of the whole journey.", cam: cam("park", 170, 10, 22, 30), fx: ["uplink"], labels: [["rooftop", "Serving cell site", B], ["parkUser", "Our user", A]] },
          { h: "Taking turns, very quickly", t: "Hundreds of phones share this cell. Every half a millisecond the site's scheduler decides which phones may transmit and on which slice of the channel. A phone with a good signal is given more.", cam: cam("park", 120, -40, 34, 10), fx: ["uplink", "beams"] },
          { h: "Aim, do not shout", t: "Rather than radiating in all directions, a 5G antenna forms a narrow beam toward each user. More of the energy arrives, and less of it interferes with anyone else.", cam: cam("downtown", 230, 10, 26, -10), fx: ["beams"] },
        ]),
        S("fibre", "Transporting Data"),
        L("The Core and Beyond", [
          { h: "Into the data centre", t: "All the city's fibre converges on one building. Here the mobile core checks who the packet belongs to and what it is allowed to do.", cam: cam("core", 170, 30, 30), fx: ["backhaul"] },
          { h: "A session and an address", t: "Before any data moved, the phone asked the core for a PDU session. The core chose a gateway (the UPF) and gave the phone an IP address. That session is the phone's standing lane to the internet.", cam: cam("core", 130, 0, 12, 22), fx: ["core"], art: "session" },
          { h: "Out, and back again", t: "The UPF hands the packet to the internet. The reply returns the same way in reverse: server, UPF, fibre, cell site, a beam of radio, the phone in the park.", cam: cam("city", 600, 200, 30, 0), fx: ["internet", "backhaul", "uplink"] },
        ]),
      ],
      quiz: [
        { type: "order", q: "Reorder the steps to show the path data takes when a phone opens a web page.", items: ["Uplink radio from the phone to the cell site", "Fibre backhaul from the site to the mobile core", "Mobile core (UPF) out to the internet", "Web server sends its reply back to the core", "Downlink radio from the cell site to the phone"], why: "Radio, backhaul, core, internet, and then the same path in reverse." },
        { type: "mc", q: "What does each packet carry besides a piece of your data?", options: ["The phone's battery level", "Source and destination addresses", "The whole web page", "The name of the cell site"], answer: 1, why: "The header carries addresses so every router knows where to forward it." },
        { type: "mc", q: "Which part of the journey is actually wireless?", options: ["Phone to cell site only", "Cell site to core", "Core to internet", "All of it"], answer: 0, why: "Only the last hop is radio. Everything behind the antenna is fibre or microwave." },
        { type: "mc", q: "Which core function forwards the user's data to the internet?", options: ["AMF", "UDM", "UPF", "NRF"], answer: 2, why: "The User Plane Function is the data gateway. The others handle signalling." },
      ],
    },
    {
      id: "call", title: "Making a Call", color: K, blurb: "What happens between pressing the green button and hearing a voice, and how the call survives a drive across town.",
      lessons: [
        L("Voice Is Just Data Now", [
          { h: "No more circuits", t: "Old networks reserved a dedicated circuit for every call. In 4G and 5G a call is simply a stream of packets, about fifty a second, each carrying 20 ms of compressed speech.", cam: cam("park", 250, 0, 34, 0), fx: ["call"] },
          { h: "But not ordinary data", t: "Voice packets are small but cannot wait. The network gives a call its own guaranteed flow, ahead of web browsing in every queue, so speech stays smooth when the cell is busy.", cam: cam("parkUser", 70, 30, 26), fx: ["call"], labels: [["parkUser", "Caller", A]] },
        ]),
        L("How the Network Finds You", [
          { h: "Registration", t: "When a phone is switched on it registers. The network authenticates the SIM and records roughly where the phone is: not the exact cell, but a tracking area of several cells.", cam: cam("city", 420, 30, 54), fx: ["cells"] },
          { h: "Paging", t: "A sleeping phone listens only briefly every second or so, to save battery. When a call arrives the core asks every cell in the tracking area to page the phone. The phone wakes and answers.", cam: cam("home", 240, -30, 40), fx: ["cells", "waves"], labels: [["home", "Called phone", A]] },
        ]),
        L("IMS: The Call Switchboard", [
          { h: "Who connects the call?", t: "A separate system, the IP Multimedia Subsystem, handles calls. The caller's phone sends it an invitation naming the number dialled. IMS finds the other phone and rings it.", cam: cam("core", 210, 20, 26, 10), fx: ["call"] },
          { h: "Signalling, then speech", t: "The set-up messages (ringing, answer, hang up) and the speech itself travel as separate flows. Once both ends agree on a voice codec, speech packets start moving in both directions.", cam: cam("city", 450, -20, 40), fx: ["call"] },
          { h: "End to end", t: "Follow the pink route: caller, rooftop site, fibre, core, fibre, the beach tower, and down to the phone in the house. Around 100 ms from mouth to ear.", cam: cam("home", 110, 40, 30), fx: ["call"], cut: ["home"], labels: [["homeUser", "Called", A]] },
        ]),
        L("Calls on the Move", [
          { h: "Measure the neighbours", t: "The amber car is on a call. Its phone constantly measures the cell it is using and the neighbouring ones, and reports the results. The thin white line shows the next-best cell.", cam: cam("city", 430, 20, 52), fx: ["handover"], labels: [["hoCar", "Car on a call", A]] },
          { h: "Handover", t: "When a neighbour becomes clearly stronger, the network prepares that cell and tells the phone to switch. The thick line changes colour as it happens. The gap is a few tens of milliseconds: nobody hears it.", cam: cam("city", 300, -10, 40), follow: "hoCar", fx: ["handover"], art: "handover", labels: [["hoCar", "Car on a call", A]] },
        ]),
      ],
      quiz: [
        { type: "mc", q: "In a 5G network a voice call is carried as…", options: ["a reserved copper circuit", "a stream of IP packets with guaranteed priority", "SMS messages", "analogue radio"], answer: 1, why: "Voice over NR is packets, given a dedicated guaranteed-bit-rate flow." },
        { type: "mc", q: "How does the network reach a sleeping phone for an incoming call?", options: ["It waits for the phone to wake", "It pages the phone across its tracking area", "It sends a satellite signal", "It cannot"], answer: 1, why: "Paging is broadcast in every cell of the tracking area where the phone last registered." },
        { type: "mc", q: "Why does a handover wait until the new cell is clearly stronger?", options: ["To avoid ping-ponging between two similar cells", "To save battery", "Because the core is slow", "To charge more"], answer: 0, why: "A margin (hysteresis) stops the phone bouncing back and forth at a cell border." },
        { type: "order", q: "Order the events in setting up a call.", items: ["Caller's phone sends an invitation to IMS", "Network pages the called phone", "Called phone rings and is answered", "A guaranteed voice flow is set up", "Speech packets flow both ways"], why: "Invite, page, answer, bearer, media." },
      ],
    },
    {
      id: "cov", title: "Mobile Coverage", color: G, blurb: "Why your signal is strong on one street and weak on the next, and the tools engineers use to fix it.",
      lessons: [
        L("What Decides Coverage", [
          { h: "Distance", t: "Signal power falls very fast with distance: double the distance and you may keep only a tenth of the power, or less in a city.", cam: cam("hilltower", 300, 20, 30, -30), fx: ["waves"] },
          { h: "Obstacles", t: "Buildings, hills and even trees block and scatter radio. The hexagons show the result: strong signal with a clear view of a site, weak in the shadows behind tall buildings.", cam: cam("downtown", 240, -20, 58, -30), fx: ["heat"], art: "heatkey" },
          { h: "Frequency", t: "The band matters too. The same site reaches three very different distances depending on the frequency it uses.", cam: cam("downtown", 470, 20, 50, -30), fx: ["spectrum"], art: "spectrum" },
        ]),
        S("smallcells", "Macro, Small and Indoor Cells"),
        L("Massive MIMO and Beamforming", [
          { h: "Many antennas acting as one", t: "A 5G panel is a grid of dozens of small antennas. By timing them precisely, the signals add up in one direction and cancel in others, forming a beam.", cam: cam("rooftop", 80, 30, 16, -8), fx: ["beams"] },
          { h: "A beam for every user", t: "The coloured cones follow cars round the block. Several users can be served on the same frequency at the same moment, because their beams do not overlap.", cam: cam("park", 190, -30, 40), fx: ["beams"], labels: [["rooftop", "Massive MIMO site", B]] },
        ]),
        S("heat", "Reading a Coverage Map"),
        S("satellite", "Reaching Beyond the Towers"),
      ],
      quiz: [
        { type: "mc", q: "You get full signal on the street but one bar behind a tall office block. The most likely cause is…", options: ["the phone is faulty", "the building is shadowing the cell site", "too many users", "the wrong SIM"], answer: 1, why: "Obstruction between you and the site is the commonest reason for local weak spots." },
        { type: "mc", q: "What is the main purpose of a small cell?", options: ["To replace the core network", "To add capacity and fill gaps in busy places", "To cover whole counties", "To power lamp posts"], answer: 1, why: "Small cells put capacity exactly where demand is concentrated." },
        { type: "mc", q: "Beamforming improves a network mainly because it…", options: ["uses more electricity", "concentrates energy on each user and reduces interference", "makes antennas taller", "removes the need for spectrum"], answer: 1, why: "Narrow beams deliver more signal to the user and less to everyone else." },
        { type: "order", q: "Order these cells from largest coverage area to smallest.", items: ["Satellite spot beam", "Rural macro cell", "City rooftop cell", "Lamp-post small cell", "Indoor ceiling cell"], why: "Hundreds of kilometres down to a single room." },
      ],
    },
    {
      id: "use", title: "4G and 5G Use Cases", color: P, blurb: "What the network is actually for: cars, factories, hospitals, farms and a million quiet sensors.",
      lessons: [
        L("Three Kinds of Service", [
          { h: "One network, three personalities", t: "5G was specified around three families of use. Broadband for people, fast and dependable links for machines, and cheap connections for vast numbers of sensors.", cam: overview, fx: ["waves"], art: "pillars" },
          { h: "Sharing without colliding", t: "All three run over the same sites and fibre. Slicing keeps them apart, so a football crowd uploading video cannot slow down a robot or drown out a fire sensor.", cam: cam("downtown", 190, 25, 34, -20), fx: ["slices"] },
        ]),
        S("av"), S("factory"), S("health"), S("city"), S("stadium"),
      ],
      quiz: [
        { type: "mc", q: "A robot arm that must receive commands within a few milliseconds needs which kind of 5G service?", options: ["eMBB", "URLLC", "mMTC", "SMS"], answer: 1, why: "Ultra-reliable low-latency communication is designed for control loops." },
        { type: "mc", q: "Ten thousand parking sensors sending a few bytes an hour is an example of…", options: ["mMTC", "eMBB", "URLLC", "fixed wireless"], answer: 0, why: "Massive machine-type communication: huge numbers, tiny messages, long battery life." },
        { type: "mc", q: "At 50 km/h, how far does a car travel during a 100 ms network delay?", options: ["About 14 cm", "About 1.4 m", "About 14 m", "About 140 m"], answer: 1, why: "50 km/h is about 14 m/s, so 0.1 s is 1.4 m." },
        { type: "mc", q: "Why is a stadium served by many narrow beams instead of one big cell?", options: ["Narrow beams look better", "So frequencies can be reused seat block by seat block", "Big cells are illegal indoors", "To save on fibre"], answer: 1, why: "Splitting the crowd into many small cells multiplies the capacity available." },
      ],
    },
    {
      id: "priv", title: "Private Wireless Networks", color: "#c4b0ff", blurb: "When a business builds a mobile network just for itself: why, how, and what it costs in complexity.",
      lessons: [
        S("port", "What Is a Private Network?"),
        L("Spectrum and Deployment Choices", [
          { h: "Whose spectrum?", t: "A private network needs frequencies. Options: licensed spectrum set aside for local use, shared bands such as CBRS, a slice of an operator's spectrum, or unlicensed bands with no protection from interference.", cam: cam("port", 230, -30, 40), fx: ["private"], art: "spectrum" },
          { h: "Whose core?", t: "The smallest set-up puts radio and core on site, fully isolated. A hybrid keeps the data path on site but shares an operator's control functions. The lightest option is simply a dedicated slice of the public network.", cam: cam("port.core", 40, -60, 24), fx: ["private"], labels: [["port.core", "On-site core", P]] },
          { h: "Why not just Wi-Fi?", t: "Wi-Fi is cheap and fine for offices. Private 5G wins where you need wide outdoor coverage, guaranteed performance, seamless mobility for vehicles, and SIM-based security.", cam: cam("yard", 200, 50, 34), fx: ["private"] },
        ]),
        S("edge"),
        S("factory", "A Private Network in a Factory"),
        S("slicing", "Slices Versus Private Networks"),
      ],
      quiz: [
        { type: "mc", q: "What makes a network private?", options: ["It uses 6G", "Its radio and capacity are dedicated to one organisation's site and devices", "It has no antennas", "It only works at night"], answer: 1, why: "Dedicated coverage, capacity and control for one organisation." },
        { type: "mc", q: "Keeping the UPF on site mainly gives…", options: ["lower latency and data that never leaves the premises", "cheaper handsets", "longer range", "more spectrum"], answer: 0, why: "A local user plane shortens the path and keeps traffic local." },
        { type: "mc", q: "In a port's private network, most traffic is…", options: ["downlink video to phones", "uplink video and telemetry from machines", "voice calls", "text messages"], answer: 1, why: "Cranes and cameras send far more than they receive." },
        { type: "order", q: "Order these options from most isolated to most shared.", items: ["Own radio, own core, own spectrum", "Own radio and local UPF, operator control plane", "Operator radio with a dedicated slice", "Ordinary public subscription"], why: "Each step trades control for simplicity." },
      ],
    },
    {
      id: "arch", title: "Network Deployment", color: "#ff93b5", blurb: "Inside the 5G system: how a base station is split, what the core functions do, and how engineers plan a network before building it.",
      lessons: [
        L("The Radio Access Network", [
          { h: "The gNB", t: "A 5G base station is called a gNB. It owns everything on the radio side: scheduling, beamforming, encryption over the air, and handovers to its neighbours.", cam: cam("hilltower", 90, 30, 14, -8), fx: ["waves"] },
          { h: "Split in three", t: "A gNB need not be one box. The radio unit stays at the antenna. The distributed unit does the split-second work nearby. The central unit, which can serve many sites, may sit kilometres away.", cam: cam("city", 420, 20, 40), fx: ["backhaul"], art: "split" },
          { h: "Open RAN", t: "Standard interfaces between those three parts let an operator buy them from different vendors and run them as software on ordinary servers. That is the idea behind Open RAN.", cam: cam("westtower", 120, 60, 24, -12), fx: ["backhaul", "waves"], art: "split" },
        ]),
        S("datacentre", "Inside the Core Data Centre"),
        S("corenet", "The 5G Core Functions"),
        L("Registration and Sessions, Step by Step", [
          { h: "Attach to the radio", t: "The phone finds the strongest cell, reads its broadcast information and requests a connection. The gNB grants it a signalling channel.", cam: cam("park", 170, 10, 22, 30), fx: ["uplink"], art: "session" },
          { h: "Prove who you are", t: "The phone sends a registration request to the AMF. The AMF asks the AUSF and UDM to challenge the SIM. Both sides prove their identity to each other, then switch on encryption.", cam: cam("core", 130, 0, 12, 22), fx: ["core"], art: "session" },
          { h: "Open a session", t: "The phone asks for a PDU session. The SMF selects a UPF, programs it with forwarding rules and returns an IP address. From now on user data flows gNB to UPF to internet.", cam: cam("core", 120, -20, 14, 22), fx: ["core", "backhaul"], art: "session" },
        ]),
        S("heat", "Planning with a Digital Twin"),
      ],
      quiz: [
        { type: "mc", q: "Which part of a split gNB stays at the antenna?", options: ["Central unit (CU)", "Distributed unit (DU)", "Radio unit (RU)", "UPF"], answer: 2, why: "The RU converts between digital samples and radio waves, right at the antenna." },
        { type: "mc", q: "Which function keeps track of where a phone is and handles its registration?", options: ["AMF", "UPF", "PCF", "NRF"], answer: 0, why: "The Access and Mobility Management Function." },
        { type: "order", q: "Order the steps a phone goes through to get online.", items: ["Connect to a cell by radio", "Register and authenticate with the AMF", "Request a PDU session from the SMF", "Receive an IP address", "Send data through the UPF"], why: "Radio first, then identity, then a session, then data." },
        { type: "mc", q: "What is a network digital twin used for?", options: ["Replacing the physical network", "Predicting coverage and testing changes before making them for real", "Storing subscriber passwords", "Charging customers"], answer: 1, why: "A twin lets you try a configuration in simulation and see the predicted result first." },
      ],
    },
  ];
})();
