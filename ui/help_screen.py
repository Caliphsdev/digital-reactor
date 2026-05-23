"""
help_screen.py — Built-in User Manual for Digital Reactor (index 8).

Layout:
    ┌─── Header ────────────────────────────────────────┐
    │ Topic sidebar (left) │ Content panel (right)       │
    │  • Getting Started   │  QTextBrowser — rich HTML   │
    │  • Reactor Science   │  with equations, diagrams,  │
    │  • How to Use…       │  step-by-step guides        │
    │  • Equations         │                             │
    │  • …                 │                             │
    └──────────────────────────────────────────────────-─┘

Content is written as HTML strings — easy to extend.
QTextBrowser renders HTML including tables, bold, italic, colour spans.
"""

import qtawesome as qta
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QTextBrowser, QFrame, QSplitter,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor

# ── Styling ────────────────────────────────────────────────────────────────────
C_HDR     = "#2c3e50"
C_TEXT    = "#ecf0f1"
C_SIDEBAR = "#f8f9fa"
C_ACTIVE  = "#2980b9"
C_BORDER  = "#dfe6e9"


# ══════════════════════════════════════════════════════════════════════════════
#  MANUAL CONTENT
#  Each topic is a (title, html_content) tuple.
#  HTML supports: <h2>, <h3>, <p>, <b>, <i>, <ul><li>, <table>, <code>,
#                 <span style="...">, <hr>, <br>
# ══════════════════════════════════════════════════════════════════════════════

def _html(body: str) -> str:
    """Wrap content in a styled HTML document."""
    return f"""
    <html><head><style>
        body   {{ font-family: 'Segoe UI', Arial, sans-serif;
                  font-size: 13px; color: #2c3e50;
                  margin: 0; padding: 0; line-height: 1.6; }}
        h2     {{ color: #2c3e50; font-size: 17px; margin-top: 8px;
                  border-bottom: 2px solid #2980b9; padding-bottom: 4px; }}
        h3     {{ color: #2980b9; font-size: 14px; margin-top: 14px; margin-bottom: 4px; }}
        h4     {{ color: #7f8c8d; font-size: 12px; margin: 10px 0 2px 0;
                  text-transform: uppercase; letter-spacing: 0.5px; }}
        p      {{ margin: 6px 0 10px 0; }}
        ul     {{ margin: 4px 0 10px 18px; padding: 0; }}
        li     {{ margin-bottom: 4px; }}
        code   {{ background: #f0f3f4; padding: 1px 5px; border-radius: 3px;
                  font-family: Consolas, monospace; font-size: 12px;
                  color: #8e44ad; }}
        .eq    {{ background: #f0f3f4; border-left: 3px solid #2980b9;
                  padding: 8px 14px; margin: 10px 0; border-radius: 0 4px 4px 0;
                  font-family: Consolas, monospace; font-size: 12px;
                  color: #2c3e50; }}
        .note  {{ background: #d5eaf9; border-left: 3px solid #2980b9;
                  padding: 8px 12px; margin: 10px 0; border-radius: 0 4px 4px 0;
                  font-size: 12px; }}
        .warn  {{ background: #fef9e7; border-left: 3px solid #e67e22;
                  padding: 8px 12px; margin: 10px 0; border-radius: 0 4px 4px 0;
                  font-size: 12px; }}
        .tip   {{ background: #d5f5e3; border-left: 3px solid #27ae60;
                  padding: 8px 12px; margin: 10px 0; border-radius: 0 4px 4px 0;
                  font-size: 12px; }}
        table  {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
        th     {{ background: #2c3e50; color: #ecf0f1; padding: 7px 10px;
                  text-align: left; font-size: 12px; }}
        td     {{ padding: 6px 10px; border-bottom: 1px solid #dfe6e9;
                  font-size: 12px; }}
        tr:nth-child(even) td {{ background: #f8f9fa; }}
        .zone-an  {{ color: #8e44ad; font-weight: bold; }}
        .zone-ax  {{ color: #2471a3; font-weight: bold; }}
        .zone-ae  {{ color: #1e8449; font-weight: bold; }}
        .zone-cl  {{ color: #7f8c8d; font-weight: bold; }}
        hr {{ border: none; border-top: 1px solid #dfe6e9; margin: 14px 0; }}
    </style></head><body>{body}</body></html>
    """


TOPICS = [

    # ── 1 ─────────────────────────────────────────────────────────────────────
    ("Getting Started", _html("""
<h2>Getting Started</h2>
<p>Welcome to <b>Digital Reactor v1.0</b> — your digital research companion for
tracking PFAS and Contaminants of Emerging Concern (CECs) through a lab-scale
activated sludge reactor.</p>

<h3>First-time Setup (5 steps)</h3>
<ul>
  <li><b>Step 1 — Create an Experiment</b><br>
      Go to <b>Experiments</b> in the sidebar. Click <i>New Experiment</i>, give
      it a name (e.g. "Run 1 – PFOS 50 µg/L"), enter the start date and the
      CECs you spiked. Click <b>Save</b>. The experiment is automatically set
      as active.</li>

  <li><b>Step 2 — Enter Today's Readings</b><br>
      Go to <b>Daily Log</b>. The date defaults to today. Fill in the core
      measurements for each reactor zone (4 tabs). Enter flow rates at the
      bottom. Click <b>Save Readings</b>.</li>

  <li><b>Step 3 — Log CEC Concentrations</b><br>
      Go to <b>CEC Tracker</b>. Select the CEC name and type, then enter
      concentrations at all four sampling points (SP1–SP4). Click <b>Save</b>.
      Removal efficiency is calculated automatically.</li>

  <li><b>Step 4 — Calculate Mass Balance</b><br>
      Go to <b>Mass Balance</b>. Select the date and click <b>Calculate</b>.
      The app uses your flow readings and CEC concentrations to compute how
      much CEC went to effluent, sludge, and transformation.</li>

  <li><b>Step 5 — Explore Predictions</b><br>
      Go to <b>Simulation</b>. Adjust the sliders to explore what-if scenarios.
      The <b>Model</b> dropdown in the top bar lets you switch between
      Phase 1 (textbook equations, always available) and Phase 2
      (your own data — requires ≥ 50 daily readings and a manual training step).</li>
</ul>

<div class="tip"><b>Tip:</b> The <b>Home</b> screen shows a live animated diagram
of your reactor plus today's Process Metrics (HRT, SRT, F:M ratio) — check it
after entering daily readings.</div>

<div class="note"><b>Data Safety:</b> Before receiving a new version of the app,
go to <b>Settings → Data Management</b> and click <b>Backup Now</b>. Your
<code>reactor.db</code> file contains all your research data.</div>
""")),

    # ── 2 ─────────────────────────────────────────────────────────────────────
    ("Reactor Overview", _html("""
<h2>Reactor Overview</h2>
<p>The Digital Reactor mirrors a <b>lab-scale Conventional Activated Sludge (CAS)
system</b> designed according to <b>OECD Guideline 303A</b>. Raw influent passes
through a Primary Settling Tank, then an Aeration Tank for biological treatment,
then a Clarifier for solids separation before discharge.</p>

<h3>Process Flow Sequence</h3>
<p>Influent enters at <b>SP1</b> and passes through four treatment stages in order:</p>

<table>
  <tr><th>Stage</th><th>Unit</th><th>Purpose</th><th>Key condition</th></tr>
  <tr>
    <td>1</td>
    <td><b>Primary Settling Tank (PST)</b></td>
    <td>Removes settleable solids and reduces TSS/COD load before biological
        treatment. Primary sludge (Q_Psludge) is withdrawn from the base.</td>
    <td>DO near 0 · low MLSS (50–500 mg/L)</td>
  </tr>
  <tr>
    <td>2</td>
    <td><span class="zone-ae">Aeration Tank</span></td>
    <td>Biological COD oxidation and nitrification (NH₄ → NO₃) by activated
        sludge. Return Activated Sludge (RAS) from the Clarifier re-enters here.</td>
    <td>DO 1.0–4.0 mg/L · MLSS 1 000–5 000 mg/L</td>
  </tr>
  <tr>
    <td>3</td>
    <td><span class="zone-cl">Clarifier (Secondary)</span></td>
    <td>Gravity settling separates biomass from treated water. Settled sludge
        recycles as RAS; excess leaves as WAS to control SRT.</td>
    <td>SVI &lt; 150 mL/g (good settling)</td>
  </tr>
  <tr>
    <td>4</td>
    <td><b>Effluent Storage</b></td>
    <td>Clarified, treated water collected before discharge or analysis at SP4.</td>
    <td>COD &lt; 100 mg/L · TSS &lt; 30 mg/L (target)</td>
  </tr>
</table>

<h3>Recycle and Sludge Streams</h3>
<ul>
  <li><b>RAS (Return Activated Sludge)</b> — settled sludge from the Clarifier
      pumped back to the Aeration Tank inlet by the Sediment Return Pump.
      Maintains biomass concentration. Design ratio: 1:1 (Q_RAS = Q_in).</li>
  <li><b>WAS (Waste Activated Sludge)</b> — excess sludge wasted from the Clarifier
      to maintain SRT at target (~30 days). Controlled via Q_WAS in the Daily Log.</li>
  <li><b>Primary Sludge (Q_Psludge)</b> — solids removed from the base of the PST.
      Entered in the Daily Log Flow Readings section.</li>
</ul>

<div class="note"><b>CAS layout:</b> This reactor uses one aeration zone with no
separate anoxic or anaerobic zones and no internal a-recycle loop. The focus is
aerobic organic removal and PFAS fate tracking, not multi-zone BNR nutrient removal.</div>

<h3>Sampling Points</h3>
<table>
  <tr><th>Point</th><th>Location</th><th>What it tells you</th></tr>
  <tr><td><b>SP1</b></td><td>Influent (feed tank)</td><td>Incoming CEC load; raw influent quality before any treatment</td></tr>
  <tr><td><b>SP2</b></td><td>After Primary Settling Tank</td><td>Removal of settleable solids; pre-biological water quality</td></tr>
  <tr><td><b>SP3</b></td><td>After Aeration Tank / Clarifier inlet</td><td>Biological treatment performance; mixed liquor quality</td></tr>
  <tr><td><b>SP4</b></td><td>Final effluent (Effluent Storage)</td><td>Overall removal efficiency; treated water discharge quality</td></tr>
</table>

<div class="note"><b>OECD 303A:</b> This reactor configuration follows OECD Guideline 303A
for activated sludge simulation tests — a standard method for assessing biodegradability
and fate of chemicals in wastewater treatment.</div>
""")),

    # ── 3 ─────────────────────────────────────────────────────────────────────
    ("Real Plant Scientific Twins", _html("""
<h2>Real Plant Scientific Twins</h2>
<p>The <b>Plants</b> page adds process-realistic Scientific Twins for selected
South African wastewater treatment plants. These pages do not replace the lab
reactor workflow; they let you compare lab-scale reactor behaviour with full
plant treatment trains using the same mass-balance thinking.</p>

<div class="warn"><b>Realism level:</b> V1 is a Scientific Twin, not a live
SCADA replica. Process layout, sampling order, HRT, SRT, MLSS, recycle logic,
pond retention, trickling-filter loading, and PFAS fate are modelled
scientifically. Exact day-by-day plant performance needs monitoring, sludge,
influent, effluent, and operations data for calibration.</div>

<h3>Plants Included in V1</h3>
<table>
  <tr><th>Plant</th><th>Process family</th><th>Visual process path</th></tr>
  <tr>
    <td><b>Daspoort</b></td>
    <td>BNR activated sludge with heritage trickling-filter research context</td>
    <td>Inlet works → PSTs → anaerobic selector → anoxic reactor → aerobic reactor → SSTs → disinfection → sludge digestion/drying beds. Heritage trickling filters are included as a research note for anammox/fixed-film interpretation.</td>
  </tr>
  <tr>
    <td><b>Zeekoegat</b></td>
    <td>Flexible BNR activated sludge</td>
    <td>Inlet works → balancing → anaerobic/anoxic/aerobic zones → SSTs → tertiary treatment → disinfection → sludge handling. BNR mode controls represent A2O/Bardenpho, UCT, Modified UCT, and Johannesburg configurations.</td>
  </tr>
  <tr>
    <td><b>Phola</b></td>
    <td>PETRO pond plus trickling-filter system</td>
    <td>Screens → vortex degritters → anaerobic ponds → trickling filter → humus tanks → disinfection → reed bed → discharge, with drying beds for sludge handling.</td>
  </tr>
</table>

<h3>Animated Visual Process Screen</h3>
<p>Each plant tab contains a large animated process overview. Treatment units
are drawn in clear hydraulic order, main water flow uses solid arrows, sludge
and PFAS-solids paths use separate coloured arrows, and sampling points pulse
after the relevant unit. Daspoort and Zeekoegat use BNR process lanes; Phola
uses pond, biofilm, humus, disinfection, reed-bed, and sludge-drying lanes.
Daspoort trickling-filter/anammox information is shown as dashed research
context, not as a normal mainline process step.</p>

<h3>Sampling, Import, and Calibration</h3>
<ul>
  <li><b>Sampling map:</b> SP1 represents influent or plant feed; SP4 represents final effluent. Intermediate points show plant-specific process checkpoints.</li>
  <li><b>Monitoring readings:</b> Plant monitoring data can store flow, COD, NH₄, TN, TP, pH, temperature, DO, MLSS, SRT, HRT, CEC name, concentration, detection limit, and below-detection flags.</li>
  <li><b>Daspoort calibration:</b> CSV/Excel import and calibration run in background threads so the interface stays responsive during larger files.</li>
  <li><b>Confidence labels:</b> Results are labelled as literature/default, partly calibrated, or calibrated depending on the data available.</li>
</ul>

<h3>Scientific Model Backbone</h3>
<p>The plant model uses mechanistic mass balance: influent load, unit-by-unit
load, effluent load, sludge/solids load, removal percentage, and unresolved or
transformed fraction. Activated-sludge/BNR modules are used for Daspoort and
Zeekoegat. Pond plus trickling-filter logic is used for Phola.</p>

<h3>PFAS Fate</h3>
<p>PFAS is treated conservatively. The model does not assume biological
destruction. It estimates water-phase passage, adsorption to sludge or captured
solids, and unresolved uncertainty. A PFAS removal number therefore means
transfer out of water, not environmental destruction.</p>

<h3>Lab Reactor vs Real Plants</h3>
<p>Use normalized operating variables to compare scale-up behaviour:
<b>HRT</b>, <b>SRT</b>, <b>F:M</b>, <b>MLSS</b>, <b>DO</b>, <b>pH</b>,
<b>temperature</b>, <b>recycle ratio</b>, <b>organic loading</b>, and
<b>nitrogen loading</b>. Measured plant data should override literature
defaults whenever available.</p>
""")),

    # ── 3 ─────────────────────────────────────────────────────────────────────
    ("Key Equations", _html("""
<h2>Key Scientific Equations</h2>
<p>All equations are implemented in <code>core/calculations.py</code> and
<code>simulation/generic_model.py</code>. This page explains each one.</p>

<hr>
<h3>1 · Mass Load (Equation 1)</h3>
<p>Converts a concentration and flow rate into a mass per day.</p>
<div class="eq">mass (µg/day) = C (µg/L) × Q (mL/h) × 24 h/day ÷ 1000 mL/L</div>
<p>Used for: influent mass load, effluent mass load, sludge mass load.</p>

<hr>
<h3>2 · Effluent Flow Rate (Equation 2)</h3>
<p>Water leaving as effluent equals what came in minus what left via sludge streams.</p>
<div class="eq">Q_eff = Q_in − Q_psludge − Q_WAS</div>
<ul>
  <li><code>Q_in</code> — influent flow (mL/h)</li>
  <li><code>Q_psludge</code> — primary sludge flow (mL/h)</li>
  <li><code>Q_WAS</code> — waste activated sludge flow (mL/h)</li>
</ul>

<hr>
<h3>3 · CEC Removal Efficiency</h3>
<div class="eq">Removal (%) = (C_inf − C_eff) / C_inf × 100</div>
<p>Where <code>C_inf</code> = SP1 concentration and <code>C_eff</code> = SP4 concentration (µg/L).</p>

<hr>
<h3>4 · Mass Balance (CEC Fate)</h3>
<p>Accounts for all destinations of the CEC in the system.</p>
<div class="eq">
Mass_transformed = Mass_in − Mass_eff − Mass_sludge
</div>
<ul>
  <li><b>Mass_in</b> = load entering at SP1</li>
  <li><b>Mass_eff</b> = load leaving at SP4 (effluent)</li>
  <li><b>Mass_sludge</b> = load leaving via WAS</li>
  <li><b>Mass_transformed</b> = biodegraded or sorbed within the reactor</li>
</ul>

<hr>
<h3>5 · Hydraulic Retention Time (HRT)</h3>
<div class="eq">HRT (h) = V_reactor (L) / Q_in (L/h) = 12 L / (Q_in_mLh / 1000 × 24)</div>
<p>At design flow of 320 mL/h: HRT ≈ 37.5 hours (≈ 1.56 days).</p>
<div class="note">HRT controls how long water stays in the reactor. Too short → incomplete treatment. Too long → over-aeration costs.</div>

<hr>
<h3>6 · Sludge Retention Time (SRT / Sludge Age)</h3>
<div class="eq">SRT (days) = V_reactor / Q_WAS (L/day)</div>
<p>Target SRT for this reactor: <b>30 days</b> (extended aeration).<br>
Minimum SRT for nitrifiers: ~5 days at 20°C (rises at lower temperatures).</p>
<div class="warn"><b>Warning:</b> If SRT falls below ~7–10 days, nitrifying bacteria
(slow-growing autotrophs) wash out of the system. Recovery takes weeks.</div>

<hr>
<h3>7 · Food-to-Microorganism (F:M) Ratio</h3>
<div class="eq">F:M = (COD_inf × Q_in) / (MLVSS × V_reactor) &nbsp; [kg COD / kg VSS / day]</div>
<ul>
  <li>MLVSS = MLSS × 0.80 (when VSS not directly measured)</li>
  <li>Target for extended aeration: <b>0.05–0.15 kg/kg/day</b></li>
  <li>Low F:M → over-aeration (high energy, good effluent)</li>
  <li>High F:M → under-aeration (poor effluent quality)</li>
</ul>

<hr>
<h3>8 · COD Removal (Phase 1 model)</h3>
<p>First-order aerobic kinetics with temperature correction:</p>
<div class="eq">
COD_removal = 1 − 1 / (1 + k_COD × HRT_days)<br><br>
k_COD = 1.2 × θ^(T − 20)   where θ = 1.06
</div>
<p><code>θ</code> is the Arrhenius temperature coefficient — increasing temperature
speeds up biological reactions; decreasing slows them.</p>

<hr>
<h3>9 · Nitrification Rate (NH₄ Removal)</h3>
<div class="eq">
NH₄_removal = min(0.98, (0.55 + DO × 0.12 + SRT × 0.01) × θ^(T−20))
</div>
<p>Nitrification requires DO ≥ 1 mg/L and is strongly temperature-dependent.
The rate halves approximately every 10°C below optimal (15–25°C range).</p>

<hr>
<h3>10 · Total Phosphorus Removal (Bio-P)</h3>
<div class="eq">
TP_removal = min(0.75, (0.30 + RAS_ratio × 0.04) × θ^(T−20))
</div>
<p>In the CAS (Conventional Activated Sludge) configuration, TP removal occurs
by luxury uptake in the Aeration Tank. Re-aeration of the Return Activated
Sludge (RAS) from the Clarifier promotes phosphorus uptake by PAOs.
A higher RAS ratio increases the fraction of re-aerated sludge recycled
back to the aeration inlet, slightly improving TP removal.</p>

<hr>
<h3>11 · PFAS Removal (Solid-Water Partitioning)</h3>
<div class="eq">
Adsorption_fraction = (Kd × MLSS_kg/L) / (1 + Kd × MLSS_kg/L)
</div>
<ul>
  <li><b>Short-chain PFAS</b> (e.g. PFBA, PFBS): Kd = 0.8 L/kg — mostly stay in water</li>
  <li><b>Long-chain PFAS</b> (e.g. PFOS, PFOA): Kd = 4.5 L/kg — strongly adsorb to sludge</li>
  <li>PFAS have very stable C–F bonds and do not biodegrade — removal is mainly via
      adsorption to activated sludge particles (transferred to WAS)</li>
</ul>
<div class="warn"><b>Important:</b> PFAS removal in activated sludge is NOT destruction.
The PFAS is concentrated in the waste sludge, not eliminated from the environment.
This is why mass balance tracking is essential for your research.</div>

<hr>
<h3>12 · Alkalinity Consumed by Nitrification</h3>
<div class="eq">Alkalinity consumed (mg CaCO₃/L) = NH₄_nitrified (mg N/L) × 7.14</div>
<p>Nitrification consumes alkalinity. If influent alkalinity is insufficient,
pH will drop and inhibit nitrifiers. Monitor <b>Alkalinity</b> in the Advanced
Measurements section of the Daily Log.</p>

<hr>
<h3>13 · Sludge Volume Index (SVI)</h3>
<div class="eq">SVI (mL/g) = Settled Volume (mL/L) / MLSS (g/L)</div>
<table>
  <tr><th>SVI range</th><th>Interpretation</th></tr>
  <tr><td>&lt; 100 mL/g</td><td>Excellent settling</td></tr>
  <tr><td>100–150 mL/g</td><td>Good settling</td></tr>
  <tr><td>150–200 mL/g</td><td>Poor settling — investigate</td></tr>
  <tr><td>&gt; 200 mL/g</td><td>Bulking sludge — serious problem</td></tr>
</table>
""")),

    # ── 4 ─────────────────────────────────────────────────────────────────────
    ("Experiments Screen", _html("""
<h2>Experiments Screen</h2>
<p>An <b>Experiment</b> represents one complete reactor run — from startup
(day 1 of feeding) to shutdown (when you stop the run). All data you enter
(daily readings, CEC concentrations, mass balance results) is linked to the
active experiment.</p>

<h3>Creating an Experiment</h3>
<ul>
  <li>Fill in the <b>Name</b> field (required). Use a descriptive name like
      <code>"Run 1 – PFOS 50 µg/L – Jan 2026"</code>.</li>
  <li>Set the <b>Start Date</b> to the day you started feeding the reactor.</li>
  <li>Enter which <b>CECs were spiked</b> (e.g. "PFOS, PFBA") and the
      <b>Spike Concentration</b> in µg/L.</li>
  <li>Click <b>Save</b>. The first experiment created is automatically set
      as <b>Active</b>.</li>
</ul>

<h3>Experiment States</h3>
<table>
  <tr><th>State</th><th>Meaning</th><th>Row colour</th></tr>
  <tr><td><b>Active</b></td><td>Currently selected — all new data links here</td><td>Green tint</td></tr>
  <tr><td><b>Running</b></td><td>Started but not the active selection</td><td>Light blue</td></tr>
  <tr><td><b>Complete</b></td><td>End date set — archived</td><td>Light grey</td></tr>
</table>

<h3>Rules</h3>
<ul>
  <li>Only <b>one experiment can be Active</b> at a time. Activating a new one
      deactivates the previous one (data is NOT deleted).</li>
  <li>Clicking <b>Mark Complete</b> sets today as the end date and locks the
      experiment for editing.</li>
  <li>Deleting an experiment <b>deletes all linked data</b> (daily readings,
      CEC readings, mass balance results). This cannot be undone — backup first.</li>
</ul>

<div class="tip"><b>Tip:</b> Start a new experiment each time you change the
spike concentration, run type, or restart the reactor after a shutdown.</div>
""")),

    # ── 5 ─────────────────────────────────────────────────────────────────────
    ("Daily Log", _html("""
<h2>Daily Log</h2>
<p>The Daily Log is where you record water quality measurements for each
reactor zone every day. It links to the active experiment.</p>

<h3>Zone Tabs</h3>
<p>There are four tabs — one per treatment stage. Measure and enter values for the
zones you sampled today. You can leave zones blank if not sampled.</p>

<table>
  <tr><th>Tab</th><th>Stage</th><th>Key parameters to monitor</th></tr>
  <tr>
    <td><b>Primary Settling</b></td>
    <td>Primary Settling Tank</td>
    <td>DO (near 0), pH, COD (incoming load), TSS (settlement performance)</td>
  </tr>
  <tr>
    <td><span class="zone-ae">Aeration Tank</span></td>
    <td>Biological treatment</td>
    <td>DO (must be 1.0–4.0), NH₄ (nitrification), COD (removal), MLSS, OUR</td>
  </tr>
  <tr>
    <td><span class="zone-cl">Clarifier</span></td>
    <td>Secondary clarifier</td>
    <td>SVI (settling quality), TSS (overflow), DO (should be low)</td>
  </tr>
  <tr>
    <td><b>Effluent</b></td>
    <td>SP4 — final treated water</td>
    <td>COD, NH₄, PO₄, turbidity, TSS (effluent quality standards)</td>
  </tr>
</table>

<h3>Core Parameters (always visible)</h3>
<table>
  <tr><th>Parameter</th><th>Unit</th><th>Notes</th></tr>
  <tr><td>DO</td><td>mg/L</td><td>Dissolved Oxygen — critical for zone verification</td></tr>
  <tr><td>pH</td><td>—</td><td>Target 6.5–8.0 for biological activity</td></tr>
  <tr><td>Temperature</td><td>°C</td><td>Target 20–25°C; affects all biological rates</td></tr>
  <tr><td>COD</td><td>mg/L</td><td>Chemical Oxygen Demand — substrate / organic load</td></tr>
  <tr><td>NH₄-N</td><td>mg/L</td><td>Ammonia nitrogen — nitrification substrate</td></tr>
  <tr><td>NO₃-N</td><td>mg/L</td><td>Nitrate — denitrification substrate</td></tr>
  <tr><td>SO₄</td><td>mg/L</td><td>Sulfate — indicator of anaerobic conditions if decreasing</td></tr>
  <tr><td>PO₄-P</td><td>mg/L</td><td>Orthophosphate — bio-P monitoring</td></tr>
  <tr><td>MLSS</td><td>mg/L</td><td>Mixed Liquor Suspended Solids — biomass concentration</td></tr>
</table>

<h3>Advanced Measurements (click ▶ to expand)</h3>
<p>These are optional — enter them only when you have lab analysis results.
Click the <b>▶ Advanced Measurements</b> toggle in any zone tab to expand.</p>
<table>
  <tr><th>Parameter</th><th>Unit</th><th>Why it matters</th></tr>
  <tr><td>VSS</td><td>mg/L</td><td>Volatile Suspended Solids — active (living) biomass</td></tr>
  <tr><td>TSS</td><td>mg/L</td><td>Total Suspended Solids — effluent quality standard</td></tr>
  <tr><td>ORP</td><td>mV</td><td>Verifies zone redox conditions (anaerobic/anoxic/aerobic)</td></tr>
  <tr><td>Alkalinity</td><td>mg CaCO₃/L</td><td>pH buffer; consumed by nitrification</td></tr>
  <tr><td>Turbidity</td><td>NTU</td><td>Effluent clarity indicator</td></tr>
  <tr><td>OUR</td><td>mg/L/h</td><td>Oxygen Uptake Rate — aerobic biological activity</td></tr>
  <tr><td>BOD₅</td><td>mg/L</td><td>Biodegradable fraction of COD</td></tr>
  <tr><td>Total-N</td><td>mg/L</td><td>Complete nitrogen balance</td></tr>
  <tr><td>Total-P</td><td>mg/L</td><td>Complete phosphorus balance</td></tr>
</table>

<h3>Flow Readings Section</h3>
<p>Enter measured flow rates at the bottom of the page. These are required
for the Mass Balance calculator and HRT/SRT calculations.</p>
<ul>
  <li><b>Q_in (Influent flow)</b> — influent pump setting (design: 320 mL/h)</li>
  <li><b>Q_WAS (Waste sludge)</b> — volume wasted from Clarifier today (mL/h);
      controls SRT — enter 0 only if no sludge was wasted.</li>
  <li><b>Q_Psludge (Primary sludge)</b> — volume removed from the PST base (mL/h)</li>
  <li><b>RAS ratio</b> — Return Activated Sludge pump ratio (design: 1.0)</li>
</ul>

<h3>Red Borders</h3>
<p>Any value <b>outside the normal operating range</b> for that zone gets a
red border and a tooltip explaining the expected range. You can still save
the value — the highlight is a warning, not a block.</p>

<div class="tip"><b>Edit mode:</b> Selecting a past date pre-fills the form
with existing readings so you can correct mistakes.</div>
""")),

    # ── 6 ─────────────────────────────────────────────────────────────────────
    ("CEC Tracker", _html("""
<h2>CEC Tracker</h2>
<p>Tracks concentrations of Contaminants of Emerging Concern (CECs) — primarily
PFAS — at all four sampling points. Removal efficiencies are calculated
automatically in real time.</p>

<h3>What are CECs?</h3>
<p>Contaminants of Emerging Concern are chemical substances detected in the
environment that are not yet regulated but may cause harm. In this research,
the focus is on <b>PFAS</b> (per- and polyfluoroalkyl substances):</p>
<ul>
  <li><b>Short-chain PFAS</b> (≤ 6 carbons): e.g. PFBA (C4), PFBS (C4), PFHxA (C6)<br>
      Low Kd → mostly stays in water → harder to remove by adsorption</li>
  <li><b>Long-chain PFAS</b> (≥ 7 carbons): e.g. PFOA (C8), PFOS (C8), PFNA (C9)<br>
      High Kd → adsorbs strongly to sludge → better removal via WAS</li>
</ul>

<h3>Entering Concentrations</h3>
<ul>
  <li>Select the <b>CEC name</b> from the dropdown (or type a new one).</li>
  <li>Select <b>Type</b>: short-chain or long-chain.</li>
  <li>Select the <b>Analysis Method</b>: TOF-MS, GC-MS, LC-MS/MS, or HPLC.</li>
  <li>Enter concentrations (µg/L) at SP1, SP2, SP3, SP4.</li>
  <li>If a reading is below the instrument detection limit, tick
      <b>"Below Detection Limit"</b> and enter the detection limit value.</li>
</ul>

<h3>Removal Efficiency Panel</h3>
<p>Updates in real time as you type — no save needed to see the calculation.</p>
<table>
  <tr><th>Row</th><th>What it shows</th></tr>
  <tr><td>SP1 → SP2</td><td>Removal through the anaerobic zone</td></tr>
  <tr><td>SP2 → SP3</td><td>Removal through biological treatment</td></tr>
  <tr><td>SP3 → SP4</td><td>Removal through clarification</td></tr>
  <tr><td><b>Overall</b></td><td>SP1 → SP4 total removal (bold)</td></tr>
</table>

<p>Colour coding: <span style="color:#1e8449"><b>Green ≥ 60%</b></span> ·
<span style="color:#e67e22"><b>Amber 30–60%</b></span> ·
<span style="color:#e74c3c"><b>Red &lt; 30%</b></span></p>

<div class="note"><b>Below Detection Limit (BDL):</b> Values below the detection
limit are stored as the detection limit value with a BDL flag. In tables they
display as <code>&lt; 0.05</code> (for example). Use BDL data carefully in
removal calculations — a BDL result at SP4 indicates very high removal but
the true value is unknown.</div>
""")),

    # ── 7 ─────────────────────────────────────────────────────────────────────
    ("Mass Balance", _html("""
<h2>Mass Balance Calculator</h2>
<p>The Mass Balance screen quantifies where each CEC goes in the treatment
process — splitting total mass load into effluent, sludge, and transformation.</p>

<h3>How to Use</h3>
<ol style="margin: 6px 0 10px 18px; padding: 0;">
  <li>Select the <b>date</b> you want to calculate for.</li>
  <li>Click <b>Calculate</b>. The app reads flow readings and CEC concentrations
      for that date from the database.</li>
  <li>Review the <b>step-by-step workings panel</b> (left) — shows each equation
      with your actual values substituted in.</li>
  <li>Review the <b>fate pie chart</b> (right) — shows % to effluent, sludge,
      and transformed.</li>
  <li>Click <b>Save Results</b> to store the calculation in the database.</li>
</ol>

<h3>Calculation Steps</h3>
<p><b>Step 1</b> — Effluent flow (Equation 2):</p>
<div class="eq">Q_eff = Q_in − Q_psludge − Q_WAS</div>

<p><b>Step 2</b> — Mass loads (Equation 1) for each stream:</p>
<div class="eq">
Mass_in      = C_SP1 × Q_in × 24 / 1000   [µg/day]<br>
Mass_eff     = C_SP4 × Q_eff × 24 / 1000  [µg/day]<br>
Mass_sludge  = C_sludge × Q_WAS × 24 / 1000
</div>

<p><b>Step 3</b> — Transformed / unaccounted mass:</p>
<div class="eq">Mass_transformed = Mass_in − Mass_eff − Mass_sludge</div>

<p><b>Step 4</b> — Overall removal:</p>
<div class="eq">Removal (%) = (C_SP1 − C_SP4) / C_SP1 × 100</div>

<div class="warn"><b>Note on C_sludge:</b> If you have not measured the CEC
concentration in the waste sludge directly, the app uses 0 for C_sludge.
This means Mass_transformed will be overestimated. Measuring sludge CEC
concentration (by extracting and analysing WAS samples) gives a more accurate
mass balance closure.</div>

<h3>Interpreting Results</h3>
<ul>
  <li><b>High % to effluent</b> → poor removal; short-chain PFAS often show this</li>
  <li><b>High % to sludge</b> → adsorption-dominated; typical of long-chain PFAS</li>
  <li><b>High % transformed</b> → either true biodegradation OR measurement error
      (check mass balance closure if % transformed is unrealistically high)</li>
</ul>
""")),

    # ── 8 ─────────────────────────────────────────────────────────────────────
    ("Simulation", _html("""
<h2>Simulation Screen</h2>
<p>The Simulation screen lets you run <b>what-if scenarios</b> — adjust
operating conditions and instantly see predicted removal efficiencies,
without touching the real reactor or waiting for lab results.</p>

<h3>Choosing a Model</h3>
<p>The <b>Model</b> dropdown in the top-right of the header lets you switch
between two prediction engines:</p>
<table>
  <tr><th>Option</th><th>What it uses</th><th>When to use it</th></tr>
  <tr>
    <td><b>Phase 1 – Equations</b></td>
    <td>Textbook formulas (OECD 303A)</td>
    <td>Always available — use from day one</td>
  </tr>
  <tr>
    <td><b>Phase 2 – Data-Driven</b></td>
    <td>Random Forest trained on your lab data</td>
    <td>After ≥ 50 complete daily readings and training the model</td>
  </tr>
</table>
<p>All sliders and influent spinboxes are the same for both models. Only the
prediction engine changes when you switch.</p>

<hr>
<h3>Phase 1 — Generic Model</h3>
<p>Uses textbook equations calibrated to the reactor design. Predictions are
directional estimates — useful from day one, but not calibrated to your
specific reactor or wastewater.</p>

<h4>What you can adjust</h4>
<table>
  <tr><th>Parameter</th><th>Range</th><th>Effect on predictions</th></tr>
  <tr><td>Influent flow</td><td>100–500 mL/h</td><td>Changes HRT → affects COD and NH₄ removal</td></tr>
  <tr><td>DO (aeration tank)</td><td>0–5 mg/L</td><td>Directly controls nitrification rate</td></tr>
  <tr><td>Sludge age (SRT)</td><td>5–60 days</td><td>Low SRT → nitrifier washout warning</td></tr>
  <tr><td>RAS ratio</td><td>0.1–4.0</td><td>Return sludge ratio; affects MLSS and clarifier load</td></tr>
  <tr><td>Temperature</td><td>15–35°C</td><td>All biological rates use θ^(T−20)</td></tr>
  <tr><td>pH</td><td>6–9</td><td>Warns if outside 6.5–8.0 optimum range</td></tr>
  <tr><td>MLSS</td><td>1 000–100 000 mg/L</td><td>Controls PFAS adsorption via Kd model</td></tr>
</table>

<h4>Influent concentrations</h4>
<p>Set the incoming concentrations of COD, NH₄, Total-P, and PFAS to match
your actual feed composition.</p>

<h3>Temperature Effect (Phase 1)</h3>
<p>All biological rates are corrected for temperature using:</p>
<div class="eq">Rate_T = Rate_20°C × θ^(T − 20)   where θ = 1.06</div>
<p>A 5°C drop from 20°C to 15°C reduces all biological rates by about 25%.
This is why winter performance is typically worse.</p>

<h3>Warning Flags</h3>
<p>Yellow warning boxes appear when parameters are outside the optimal range.
Key warnings to watch for:</p>
<ul>
  <li><b>Nitrifier washout risk</b> — SRT too low for the current temperature</li>
  <li><b>DO out of range</b> — below 1 mg/L impairs nitrification</li>
  <li><b>Temperature too low/high</b> — outside 18–28°C optimum</li>
  <li><b>Flow too high</b> — reduces HRT, reduces treatment efficiency</li>
  <li><b>Phase 2 fallback</b> — if Phase 2 is selected but a model is not trained
      yet, this warning tells you which targets are still using Phase 1 equations</li>
</ul>

<hr>
<h3>Phase 2 — Data-Driven Model</h3>
<p>Phase 2 trains a <b>Random Forest</b> on your own lab measurements and uses it
to predict removal efficiencies calibrated to <i>your specific reactor</i>.</p>

<h4>Step 1 — Collect data</h4>
<p>Phase 2 requires <b>≥ 50 complete daily readings</b> — days where you entered
aerobic zone readings, effluent zone readings, and flow readings on the same date.
The Phase 2 status card (visible when Phase 2 is selected) shows your current
count vs the 50-sample threshold.</p>
<p>A separate <b>PFAS model</b> activates once you have ≥ 15 paired CEC readings
(SP1 + SP4 on the same date for the same CEC). Until then, PFAS predictions fall
back to Phase 1.</p>

<h4>Step 2 — Train the model</h4>
<ol style="margin:4px 0 10px 18px; padding:0;">
  <li>Select <b>Phase 2 – Data-Driven</b> from the Model dropdown.</li>
  <li>The status card appears below the header. When your sample count
      reaches 50, the <b>Train Model</b> button turns green and becomes clickable.</li>
  <li>Click <b>Train Model</b>. Training runs in the background (a few seconds).
      A summary popup confirms completion.</li>
  <li>After training, the status card shows R² scores and the date trained.
      The sliders immediately start using Phase 2 predictions.</li>
</ol>

<h4>Phase 2 status card</h4>
<table>
  <tr><th>Item</th><th>What it means</th></tr>
  <tr><td>Samples: X / 50</td><td>How many complete training rows are available</td></tr>
  <tr><td>Trained: date UTC</td><td>When the model was last trained</td></tr>
  <tr><td>R² COD / NH₄ / TP / PFAS</td><td>In-sample accuracy scores (see below)</td></tr>
  <tr><td>Orange status message</td><td>Why the Train button is disabled (if it is)</td></tr>
  <tr><td>Train Model / Retrain</td><td>Trigger training (green = ready, grey = not enough data)</td></tr>
</table>

<h4>Understanding R² scores</h4>
<p>After training, the popup shows a <b>cross-validated R²</b> — the scientifically
meaningful accuracy score. The status card shows per-target in-sample R² values.</p>
<table>
  <tr><th>Cross-validated R²</th><th>What it means</th></tr>
  <tr><td>&gt; 0.80</td><td>Strong model — captures your reactor's behaviour well</td></tr>
  <tr><td>0.60 – 0.80</td><td>Acceptable — useful with some uncertainty</td></tr>
  <tr><td>&lt; 0.60</td><td>Weak — may need more data or check for data entry errors</td></tr>
</table>
<div class="note"><b>Note:</b> The per-target R² values shown in the status card
(e.g. COD 0.96) are in-sample scores and will always look high. The cross-validated
R² in the training popup is the honest measure — use that to judge model quality.</div>

<h4>When to retrain</h4>
<p>Click <b>Retrain</b> after collecting several more weeks of data to incorporate
new measurements. There is no harm in retraining frequently — the model always
trains on the full dataset.</p>

<hr>
<h3>Saving a Scenario</h3>
<p>Click <b>Save Scenario</b> to store the current inputs and predictions in the
database. The record is tagged <code>generic</code> (Phase 1) or
<code>data_driven</code> (Phase 2) so the Comparison dashboard can distinguish them.</p>
""")),

    # ── 9 ─────────────────────────────────────────────────────────────────────
    ("Comparison Dashboard", _html("""
<h2>Comparison Dashboard</h2>
<p>The Comparison Dashboard displays four chart tabs for visualising trends
and comparing your lab reactor against the full-scale Daspoort WWTP.</p>

<h3>Tab 1 — Lab vs Daspoort</h3>
<p>Plots removal efficiency (%) over time for both your lab reactor and
the corresponding Daspoort WWTP quarterly monitoring data. Select a specific
CEC from the dropdown to filter the chart.</p>
<p>This is the core comparison of your PhD research — how does a controlled
lab system track the performance of a real treatment plant?</p>

<h3>Tab 2 — Model vs Actual</h3>
<p>Compares Phase 1 simulation predictions (dotted line) against your measured
lab data (solid line). As more data accumulates, you can see how well the
generic model tracks reality — and where it diverges.</p>

<h3>Tab 3 — CEC Concentration Trends</h3>
<p>Plots CEC concentration (µg/L) at each of the four sampling points over
the experiment duration. Shows how the treatment train progressively removes
the contaminant day by day.</p>

<h3>Tab 4 — Parameter Trends</h3>
<p>Plots daily water quality parameters (DO, pH, COD, NH₄) for each zone
over time. Useful for spotting process upsets, seasonal trends, or the
effect of operational changes.</p>

<h3>Daspoort Data Entry</h3>
<p>Quarterly field samples from Daspoort WWTP should be entered manually
in the <b>Settings screen</b> or imported via CSV (coming in a future update).
Without Daspoort data, Tab 1 will show only the lab data line.</p>

<h3>Exporting Charts</h3>
<p>Click the <b>Export PNG</b> button in the header to save all four charts
as PNG image files. These can be inserted directly into your thesis or
conference papers.</p>
""")),

    # ── 10 ────────────────────────────────────────────────────────────────────
    ("Process Metrics Card", _html("""
<h2>Process Metrics Card (Home Screen)</h2>
<p>At the bottom of the Home screen, below the reactor diagram, is a
collapsible <b>▶ Process Metrics</b> strip. Click it to expand and see
today's calculated process performance indicators.</p>

<h3>Displayed Metrics</h3>
<table>
  <tr><th>Metric</th><th>What it shows</th><th>Target (this reactor)</th></tr>
  <tr>
    <td><b>HRT</b></td>
    <td>Hydraulic Retention Time — how long water stays in the reactor</td>
    <td>~37.5 h at 320 mL/h</td>
  </tr>
  <tr>
    <td><b>Actual SRT</b></td>
    <td>Sludge age — calculated from today's Q_WAS flow</td>
    <td>30 days (target)</td>
  </tr>
  <tr>
    <td><b>F:M Ratio</b></td>
    <td>Food-to-Microorganism — organic load vs biomass</td>
    <td>0.05–0.15 kg/kg/day</td>
  </tr>
</table>

<h3>Colour Codes</h3>
<ul>
  <li><span style="color:#27ae60"><b>Green</b></span> — value is within target range</li>
  <li><span style="color:#e67e22"><b>Amber</b></span> — value is outside target range, attention needed</li>
</ul>

<h3>Nitrifier Washout Warning</h3>
<p>If the actual SRT is below the minimum safe value for the current reactor
temperature, an orange warning message appears in the metrics strip. Take
action immediately — reduce Q_WAS to increase SRT.</p>

<div class="note"><b>Data required:</b> These metrics need today's flow readings
(Q_in and Q_WAS) to be saved in the Daily Log. If they show "—" it means
no flow data has been entered for today yet.</div>
""")),

    # ── 11 ────────────────────────────────────────────────────────────────────
    ("Settings & Data Backup", _html("""
<h2>Settings & Data Backup</h2>
<p>The Settings screen (gear icon at the bottom of the sidebar) has three tabs.</p>

<h3>Tab 1 — Data Management</h3>
<p>This is the most important tab for data safety.</p>

<p><b>Backup Database</b><br>
Clicking <b>Backup Now</b> creates a timestamped copy of your database:</p>
<div class="eq">reactor_backup_2026-04-08_14-30-00.db</div>
<p>Backups are stored in a <code>backups/</code> folder next to <code>reactor.db</code>.
The last 5 backups are kept automatically.</p>

<p><b>When to backup:</b></p>
<ul>
  <li>Before installing a new version of the app</li>
  <li>Before deleting an experiment</li>
  <li>After completing a major experimental milestone</li>
  <li>Weekly as a routine (enable Auto-backup)</li>
</ul>

<p><b>Auto-backup toggle</b> — when ON, a backup is created automatically each
time you open the Settings screen.</p>

<p><b>Restore</b> — select a backup from the history list and click
<b>Restore Selected Backup</b>. This overwrites the current database.
<b>Restart the app after restoring.</b></p>

<div class="warn"><b>Warning:</b> Restoring a backup replaces all current data
with the backup's data. Any readings entered after the backup was made will be
lost. Always create a fresh backup of the current state before restoring an
old one.</div>

<p><b>Export to Excel</b> — exports every database table to a single
<code>.xlsx</code> workbook, one sheet per table. Use this for external
analysis in Excel, R, or Python.</p>

<h3>Tab 2 — Simulation Defaults</h3>
<p>Set the default values that pre-fill the Simulation screen sliders when
the app opens. Set these to your typical reactor operating conditions so you
do not have to adjust sliders every time.</p>

<h3>Tab 3 — About</h3>
<p>Shows version number, researcher details, developer contact, and the
full path to the database file.</p>

<h3>Schema Migrations (automatic)</h3>
<p>When a new app version adds new database columns, the migration system
runs automatically on startup and adds the columns to your existing
<code>reactor.db</code>. Your data is never deleted. New columns appear as
blank (<code>—</code>) for old readings until you enter values.</p>
""")),

    # ── 12 ────────────────────────────────────────────────────────────────────
    ("Parameter Reference", _html("""
<h2>Parameter Reference Guide</h2>
<p>Quick-reference card for all measured parameters, their units, and
the expected ranges for this reactor system.</p>

<h3>Water Quality — Normal Operating Ranges</h3>
<table>
  <tr><th>Parameter</th><th>Unit</th><th>Primary Settling</th><th>Aeration Tank</th><th>Clarifier</th><th>Effluent</th></tr>
  <tr><td>DO</td><td>mg/L</td><td>0–1.0</td><td><b>1.0–4.0</b></td><td>0–2.0</td><td>—</td></tr>
  <tr><td>pH</td><td>—</td><td>6.5–8.5</td><td>6.5–8.0</td><td>6.5–8.5</td><td>6.0–9.0</td></tr>
  <tr><td>Temperature</td><td>°C</td><td>15–30</td><td>18–28</td><td>15–30</td><td>15–30</td></tr>
  <tr><td>COD</td><td>mg/L</td><td>50–3000</td><td>5–500</td><td>5–200</td><td>&lt;100</td></tr>
  <tr><td>NH₄-N</td><td>mg/L</td><td>0–200</td><td>0–50</td><td>0–30</td><td>&lt;30</td></tr>
  <tr><td>NO₃-N</td><td>mg/L</td><td>0–50</td><td>0–100</td><td>0–50</td><td>&lt;30</td></tr>
  <tr><td>PO₄-P</td><td>mg/L</td><td>0–50</td><td>0–30</td><td>0–20</td><td>&lt;10</td></tr>
  <tr><td>MLSS</td><td>mg/L</td><td>50–500</td><td>1 000–5 000</td><td>—</td><td>&lt;30</td></tr>
  <tr><td>ORP</td><td>mV</td><td>—</td><td>+50 to +200</td><td>—</td><td>—</td></tr>
</table>

<h3>Flow Rates</h3>
<table>
  <tr><th>Parameter</th><th>Unit</th><th>Design value</th><th>Operating range</th></tr>
  <tr><td>Q_in (influent)</td><td>mL/h</td><td>320</td><td>200–450</td></tr>
  <tr><td>Q_WAS (waste sludge)</td><td>mL/h</td><td>—</td><td>0–200 (set to achieve SRT 30 d)</td></tr>
  <tr><td>Q_Psludge (primary sludge)</td><td>mL/h</td><td>—</td><td>0–200</td></tr>
  <tr><td>RAS ratio</td><td>—</td><td>1.0</td><td>0.5–2.0</td></tr>
  <tr><td>SRT</td><td>days</td><td>30</td><td>20–40</td></tr>
</table>

<h3>PFAS Partitioning (Kd values)</h3>
<table>
  <tr><th>PFAS type</th><th>Examples</th><th>Kd (L/kg)</th><th>Expected removal</th></tr>
  <tr><td>Short-chain</td><td>PFBA, PFBS, PFHxA</td><td>0.8</td><td>Low (5–25%)</td></tr>
  <tr><td>Long-chain</td><td>PFOS, PFOA, PFNA</td><td>4.5</td><td>Moderate (15–60%)</td></tr>
</table>

<h3>Sludge Quality</h3>
<table>
  <tr><th>Parameter</th><th>Unit</th><th>Target</th><th>Alarm</th></tr>
  <tr><td>SVI₃₀</td><td>mL/g</td><td>&lt; 120</td><td>&gt; 150 (bulking)</td></tr>
  <tr><td>VSS/MLSS ratio</td><td>—</td><td>0.75–0.85</td><td>&lt; 0.60 (inert accumulation)</td></tr>
  <tr><td>OUR</td><td>mg/L/h</td><td>5–60</td><td>&lt; 5 (low activity)</td></tr>
  <tr><td>F:M</td><td>kg/kg/d</td><td>0.05–0.15</td><td>&gt; 0.3 (overloaded)</td></tr>
</table>

<h3>Abbreviations</h3>
<table>
  <tr><th>Abbreviation</th><th>Full name</th></tr>
  <tr><td>AS</td><td>Activated Sludge</td></tr>
  <tr><td>CAS</td><td>Conventional Activated Sludge</td></tr>
  <tr><td>PST</td><td>Primary Settling Tank</td></tr>
  <tr><td>BOD</td><td>Biochemical Oxygen Demand</td></tr>
  <tr><td>CEC</td><td>Contaminant of Emerging Concern</td></tr>
  <tr><td>COD</td><td>Chemical Oxygen Demand</td></tr>
  <tr><td>DO</td><td>Dissolved Oxygen</td></tr>
  <tr><td>F:M</td><td>Food-to-Microorganism ratio</td></tr>
  <tr><td>HRT</td><td>Hydraulic Retention Time</td></tr>
  <tr><td>Kd</td><td>Solid-water partition coefficient</td></tr>
  <tr><td>MLSS</td><td>Mixed Liquor Suspended Solids</td></tr>
  <tr><td>MLVSS</td><td>Mixed Liquor Volatile Suspended Solids</td></tr>
  <tr><td>ORP</td><td>Oxidation-Reduction Potential</td></tr>
  <tr><td>OUR</td><td>Oxygen Uptake Rate</td></tr>
  <tr><td>PAO</td><td>Phosphorus Accumulating Organism</td></tr>
  <tr><td>PFAS</td><td>Per- and Polyfluoroalkyl Substances</td></tr>
  <tr><td>RAS</td><td>Return Activated Sludge</td></tr>
  <tr><td>SOUR</td><td>Specific Oxygen Uptake Rate</td></tr>
  <tr><td>SP</td><td>Sampling Point</td></tr>
  <tr><td>SRT</td><td>Solids Retention Time (Sludge Age)</td></tr>
  <tr><td>SVI</td><td>Sludge Volume Index</td></tr>
  <tr><td>TSS</td><td>Total Suspended Solids</td></tr>
  <tr><td>VSS</td><td>Volatile Suspended Solids</td></tr>
  <tr><td>WAS</td><td>Waste Activated Sludge</td></tr>
  <tr><td>WWTP</td><td>Wastewater Treatment Plant</td></tr>
</table>
""")),

    # ── 13 ────────────────────────────────────────────────────────────────────
    ("Troubleshooting", _html("""
<h2>Troubleshooting</h2>

<h3>App won't start / database error</h3>
<ul>
  <li>Make sure the app folder is not inside a read-only location (e.g. Program Files).</li>
  <li>Check that <code>reactor.db</code> is not open in another program (e.g. DB Browser for SQLite).</li>
  <li>Try running as Administrator if on a restricted university machine.</li>
</ul>

<h3>All fields show "—" after navigating to Daily Log</h3>
<ul>
  <li>There is no active experiment. Go to <b>Experiments</b> and set one as Active.</li>
  <li>Or you selected a date with no existing readings — this is normal for new dates.</li>
</ul>

<h3>Mass Balance says "No flow readings for this date"</h3>
<ul>
  <li>Go to <b>Daily Log</b>, select the same date, scroll to the Flow Readings
      section, enter the values, and click <b>Save Readings</b>.</li>
</ul>

<h3>CEC removal efficiency shows 0% or negative</h3>
<ul>
  <li>Check that SP1 (influent) concentration is greater than SP4 (effluent).
      If SP4 > SP1, the result is shown as 0% (not negative).</li>
  <li>Negative apparent removal can happen with BDL values — check if SP1 is BDL.</li>
</ul>

<h3>Simulation predictions seem too high/low</h3>
<ul>
  <li>Phase 1 is a generic model — it is an estimate, not a measurement.</li>
  <li>Check that your influent concentrations in the slider panel match your
      actual measured values.</li>
  <li>Temperature has a large effect — verify the temperature setting is correct.</li>
</ul>

<h3>Phase 2 "Train Model" button is greyed out</h3>
<ul>
  <li>You need <b>≥ 50 complete daily readings</b>. A complete row means aerobic zone,
      effluent zone, and flow readings all saved on the same date.</li>
  <li>The status card shows your current count (e.g. "Samples: 23 / 50 required").
      Keep entering daily data.</li>
  <li>Rows where Q_WAS = 0 are excluded (SRT cannot be computed). Enter a non-zero
      waste sludge flow in the Daily Log → Flow Readings section.</li>
</ul>

<h3>Phase 2 training failed</h3>
<ul>
  <li>An error message will appear in the status card. The most common cause is a
      data quality issue — values that are identical across all rows (no variation)
      prevent the model from learning.</li>
  <li>Check that your aerobic and effluent zone readings are different across
      different days (i.e. the reactor conditions actually varied over time).</li>
  <li>Try again after entering more data from different operating conditions.</li>
</ul>

<h3>Phase 2 cross-validated R² is below 0.60</h3>
<ul>
  <li>This means the model is not reliably predicting from the available data.
      Common causes: too little data (close to the 50-sample minimum), inconsistent
      measurements, or operating conditions that barely changed across experiments.</li>
  <li>Continue collecting data and retrain when you have 100+ samples.</li>
  <li>Meanwhile, use Phase 1 — it is still scientifically valid.</li>
</ul>

<h3>Phase 2 selected but predictions look the same as Phase 1</h3>
<ul>
  <li>If the model is not trained yet, Phase 2 silently falls back to Phase 1.
      A yellow warning in the results area confirms this. Train the model first.</li>
  <li>If the PFAS model is not yet trained (fewer than 15 CEC readings), PFAS
      predictions always fall back to Phase 1 even when the main model is active.</li>
</ul>

<h3>Process Metrics card shows "—" for SRT</h3>
<ul>
  <li>SRT requires a non-zero Q_WAS (waste sludge flow). If Q_WAS = 0, SRT is
      mathematically infinite (no sludge wasting). Enter the actual WAS volume
      removed today in the Daily Log → Flow Readings section.</li>
</ul>

<h3>Backup restore failed</h3>
<ul>
  <li>Close the app completely, manually copy the backup file from the
      <code>backups/</code> folder and rename it to <code>reactor.db</code>
      in the main app folder. Then restart the app.</li>
</ul>

<h3>Contact the developer</h3>
<p>If you encounter a bug or need assistance:</p>
<p><b>Caliphs Zvinowanda</b><br>
<b>Phone:</b> +27 65 235 7607</p>
""")),

]


# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN WIDGET
# ══════════════════════════════════════════════════════════════════════════════

class HelpScreen(QWidget):
    """Built-in user manual with topic sidebar and HTML content panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_header())

        # Splitter: sidebar | content
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #dfe6e9; }")

        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_content())
        splitter.setSizes([220, 900])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, stretch=1)

        # Show first topic by default
        self._topic_list.setCurrentRow(0)

    # ── Header ─────────────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background-color: {C_HDR};")
        row = QHBoxLayout(bar)
        row.setContentsMargins(18, 0, 18, 0)
        row.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(qta.icon("fa6s.book-open", color="#ecf0f1").pixmap(QSize(20, 20)))
        row.addWidget(icon_lbl)

        title = QLabel("User Manual")
        f = QFont(); f.setPointSize(13); f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {C_TEXT};")
        row.addWidget(title)
        row.addStretch()

        sub = QLabel("Digital Reactor v1.0  ·  Reference & Process Guide")
        sub.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        row.addWidget(sub)

        return bar

    # ── Topic sidebar ──────────────────────────────────────────────────────────
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setMinimumWidth(200)
        sidebar.setMaximumWidth(260)
        sidebar.setStyleSheet(f"background: {C_SIDEBAR}; border-right: 1px solid {C_BORDER};")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Section label
        hdr = QLabel("  Topics")
        hdr.setFixedHeight(34)
        hdr.setStyleSheet(
            f"background: #dfe6e9; color: #7f8c8d; font-size: 10px; "
            f"font-weight: bold; letter-spacing: 0.5px; "
            f"border-bottom: 1px solid {C_BORDER};"
        )
        layout.addWidget(hdr)

        self._topic_list = QListWidget()
        self._topic_list.setFrameShape(QFrame.NoFrame)
        self._topic_list.setStyleSheet(f"""
            QListWidget {{
                background: {C_SIDEBAR};
                border: none;
                font-size: 11px;
                color: #2c3e50;
                outline: none;
            }}
            QListWidget::item {{
                padding: 9px 16px;
                border-bottom: 1px solid #ecf0f1;
            }}
            QListWidget::item:selected {{
                background: {C_ACTIVE};
                color: white;
                border-left: 3px solid #1a6da3;
            }}
            QListWidget::item:hover:!selected {{
                background: #d5eaf9;
            }}
        """)

        for title, _ in TOPICS:
            item = QListWidgetItem(title)
            self._topic_list.addItem(item)

        self._topic_list.currentRowChanged.connect(self._on_topic_selected)
        layout.addWidget(self._topic_list, stretch=1)

        return sidebar

    # ── Content panel ──────────────────────────────────────────────────────────
    def _build_content(self) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: #ffffff;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(False)
        self._browser.setFrameShape(QFrame.NoFrame)
        self._browser.setStyleSheet("""
            QTextBrowser {
                background: #ffffff;
                border: none;
                padding: 20px 28px;
                font-size: 13px;
            }
        """)
        # Override the document margin for inner padding
        self._browser.document().setDocumentMargin(24)

        layout.addWidget(self._browser)
        return container

    # ── Navigation ─────────────────────────────────────────────────────────────
    def _on_topic_selected(self, index: int) -> None:
        if 0 <= index < len(TOPICS):
            _, html = TOPICS[index]
            self._browser.setHtml(html)
            self._browser.verticalScrollBar().setValue(0)
