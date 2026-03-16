const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, LevelFormat,
  HeadingLevel, BorderStyle, WidthType, ShadingType,
  PageNumber, PageBreak,
} = require("docx");

const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 80, bottom: 80, left: 120, right: 120 };

function headerCell(text, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: "1E3A5F", type: ShadingType.CLEAR },
    margins: cellMargins,
    verticalAlign: "center",
    children: [new Paragraph({ children: [new TextRun({ text, bold: true, color: "FFFFFF", font: "Arial", size: 20 })] })],
  });
}

function cell(text, width, opts = {}) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: opts.shade ? { fill: "F5F7FA", type: ShadingType.CLEAR } : undefined,
    margins: cellMargins,
    children: [new Paragraph({ children: [new TextRun({ text, font: "Arial", size: 20, bold: opts.bold })] })],
  });
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: "1E3A5F" },
        paragraph: { spacing: { before: 360, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 1 },
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "404040" },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 },
      },
    ],
  },
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets2",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets3",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets4",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets5",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets6",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets7",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
      {
        reference: "bullets8",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } },
        }],
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
        },
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 } },
            children: [new TextRun({ text: "DC Feasibility Tool v4 \u2014 Results Dashboard Features", font: "Arial", size: 18, color: "888888" })],
          })],
        }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            border: { top: { style: BorderStyle.SINGLE, size: 4, color: "CCCCCC", space: 1 } },
            children: [
              new TextRun({ text: "Page ", font: "Arial", size: 18, color: "888888" }),
              new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: "888888" }),
            ],
          })],
        }),
      },
      children: [
        // ── Title Page ──
        new Paragraph({ spacing: { before: 2400 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ text: "DC Feasibility Tool v4", font: "Arial", size: 52, bold: true, color: "1E3A5F" })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 200 },
          children: [new TextRun({ text: "Results Dashboard \u2014 Feature Reference", font: "Arial", size: 32, color: "2E75B6" })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 600 },
          children: [new TextRun({ text: "Version 4.1.4  |  March 2026", font: "Arial", size: 22, color: "888888" })],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 200 },
          children: [new TextRun({ text: "A comprehensive guide to every feature, metric, and analysis tool\navailable in the Results Dashboard.", font: "Arial", size: 22, color: "666666" })],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ── Table of Contents placeholder ──
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Table of Contents")] }),
        new Paragraph({ children: [new TextRun({ text: "1. Overview", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "2. Results Table", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "3. Tab 1: Overview", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "4. Tab 2: Capacity & PUE", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "5. Tab 3: Infrastructure", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "6. Tab 4: Sensitivity", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "7. Tab 5: Expansion", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "8. Tab 6: Firm Capacity", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "9. Scoring System", font: "Arial", size: 22 })] }),
        new Paragraph({ children: [new TextRun({ text: "10. Glossary", font: "Arial", size: 22 })] }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 1. OVERVIEW
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("1. Overview")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The Results Dashboard is the central analysis interface of the DC Feasibility Tool. After running one or more scenarios through the Scenario Runner (either Guided Mode or Advanced Mode), all results appear here ranked by a composite feasibility score. The dashboard provides a full-width results table at the top and a tab-based detail panel below for in-depth analysis of any selected scenario."
          )],
        }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The dashboard supports two PUE calculation modes: a static mode (using lookup-table PUE values) and an hourly mode (full 8,760-hour climate simulation using site-specific weather data). The hourly mode unlocks additional features like daily operating profiles, PUE decomposition, firm capacity analysis, and climate-specific IT capacity commitments."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Key Concepts")] }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "RAG Status: ", bold: true }), new TextRun("A Red/Amber/Green/Blue traffic-light rating indicating site viability. RED = not viable, AMBER = marginal, GREEN = feasible, BLUE = excellent.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "Composite Score: ", bold: true }), new TextRun("A 0\u2013100 weighted score combining PUE efficiency, IT capacity, space utilization, rack deployment ratio, and RAG status.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "Committed IT (P99): ", bold: true }), new TextRun("In hourly mode, the IT load you can contractually guarantee 99% of hours in the year. In static mode, the nominal IT load from the power model.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets", level: 0 },
          children: [new TextRun({ text: "Binding Constraint: ", bold: true }), new TextRun("Whether the scenario is limited by available electrical POWER or physical SPACE. This determines which expansion strategies are effective.")],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 2. RESULTS TABLE
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("2. Results Table")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The full-width results table displays all scenarios from the most recent batch run. Results are pre-sorted by composite score (highest first). Clicking any row opens the detail panel below."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Table Columns")] }),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [2000, 7360],
          rows: [
            new TableRow({ children: [headerCell("Column", 2000), headerCell("Description", 7360)] }),
            new TableRow({ children: [cell("# (Rank)", 2000, { bold: true }), cell("Position in the score-ranked list. Rank 1 = best composite score.", 7360)] }),
            new TableRow({ children: [cell("Site", 2000, { bold: true, shade: true }), cell("The site name as entered in Site Manager.", 7360, { shade: true })] }),
            new TableRow({ children: [cell("Load", 2000, { bold: true }), cell("Load type (e.g., Colocation Standard, AI/GPU, HPC, Hyperscale, Edge/Telco).", 7360)] }),
            new TableRow({ children: [cell("Cooling", 2000, { bold: true, shade: true }), cell("Cooling topology used (e.g., Air-Cooled Chiller + Economizer, DLC, RDHx, Dry Cooler).", 7360, { shade: true })] }),
            new TableRow({ children: [cell("IT Commit (MW)", 2000, { bold: true }), cell("The committable IT load in megawatts. Uses P99 from hourly simulation when available, otherwise nominal static IT load.", 7360)] }),
            new TableRow({ children: [cell("PUE", 2000, { bold: true, shade: true }), cell("Power Usage Effectiveness. Energy-weighted annual PUE from hourly simulation, or static lookup PUE.", 7360, { shade: true })] }),
            new TableRow({ children: [cell("Racks", 2000, { bold: true }), cell("Number of racks deployed based on whitespace, floor count, and rack density.", 7360)] }),
            new TableRow({ children: [cell("RAG", 2000, { bold: true, shade: true }), cell("Traffic-light status: RED (not viable), AMBER (warning), GREEN (good), BLUE (excellent).", 7360, { shade: true })] }),
            new TableRow({ children: [cell("Score", 2000, { bold: true }), cell("Composite feasibility score (0\u2013100). Higher is better.", 7360)] }),
          ],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 3. TAB 1: OVERVIEW
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("3. Tab 1: Overview")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The Overview tab provides a snapshot of the selected scenario\u2019s key metrics. It is the default view when you click a result row."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Key Metrics Grid")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Displays a responsive grid of metric cards:")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Committed IT (P99) / IT Load: ", bold: true }), new TextRun("The sellable IT capacity. In hourly mode, this is the P99 value (guaranteed 99% of hours). In static mode, the nominal IT load.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Worst-Hour IT: ", bold: true }), new TextRun("The minimum IT capacity across all 8,760 hours (hourly mode only). Represents the absolute worst case.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Annual Mean IT: ", bold: true }), new TextRun("Average IT capacity across the year (hourly mode only).")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Nominal IT: ", bold: true }), new TextRun("The static-model IT load, shown for comparison with hourly results.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Facility Power: ", bold: true }), new TextRun("Total electrical load including IT, cooling, lighting, and losses.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Procurement Power: ", bold: true }), new TextRun("Grid capacity needed, including procurement safety factor.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "PUE: ", bold: true }), new TextRun("Power Usage Effectiveness with source label (hourly or static).")],
        }),
        new Paragraph({
          numbering: { reference: "bullets2", level: 0 },
          children: [new TextRun({ text: "Racks, Rack Density, Constraint, Score: ", bold: true }), new TextRun("Deployed rack count, per-rack power density (kW), binding constraint type, and composite score.")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Space Summary")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Shows physical space metrics: buildable footprint (m\u00B2), active floors, effective racks possible, whitespace ratio (% of floor used for IT), and site coverage ratio (% of land used by building).")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("IT Capacity Spectrum Chart")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun("Visible only in hourly mode. A bar chart showing the distribution of IT capacity across 8,760 hours: worst hour, P1, P5, P50 (median), P95, P99, and best hour. This visualizes how much the site\u2019s IT capacity varies with weather conditions throughout the year.")],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 4. TAB 2: CAPACITY & PUE
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("4. Tab 2: Capacity & PUE")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "This tab provides detailed analysis of how IT capacity and PUE fluctuate throughout the year. Both features require hourly weather simulation (not available in static PUE mode)."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Daily Operating Profiles")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Click \"Load\" to fetch daily aggregated profiles. The engine groups 8,760 hourly values into representative days and displays two side-by-side charts:")],
        }),
        new Paragraph({
          numbering: { reference: "bullets3", level: 0 },
          children: [new TextRun({ text: "Daily IT Load Chart: ", bold: true }), new TextRun("Shows min/mean/max IT capacity per representative day, with a reference line at the P99 committed IT level.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets3", level: 0 },
          children: [new TextRun({ text: "Daily PUE Chart: ", bold: true }), new TextRun("Shows min/mean/max PUE per representative day, with a reference line at the annual energy-weighted PUE.")],
        }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Summary metrics include committed IT, annual mean IT, peak daily IT, worst/best hour IT, peak daily PUE, annual PUE, and the number of representative days.")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("PUE Overhead Decomposition")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "Click \"Compute\" to break down the annual PUE overhead into its constituent components. Shows total overhead energy (kWh), total facility energy, and total IT energy. Each component (mechanical cooling, economizer, pumps, lighting, UPS losses, misc fixed loads) is displayed as a labeled bar with its share of total overhead as a percentage. Also shows the number of hours spent in each cooling mode: mechanical-only (MECH), partial economizer (ECON_PART), full economizer (ECON_FULL), and overtemperature hours."
          )],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 5. TAB 3: INFRASTRUCTURE
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("5. Tab 3: Infrastructure")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The Infrastructure tab calculates physical space requirements for all major data center equipment and compares backup power technologies."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Infrastructure Footprint")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Calculates the ground-level and rooftop area needed for transformers, switchgear, cooling equipment, backup generators, fuel storage, and other infrastructure. Inputs:")],
        }),
        new Paragraph({
          numbering: { reference: "bullets4", level: 0 },
          children: [new TextRun({ text: "Backup Technology: ", bold: true }), new TextRun("Select from Diesel Genset, Natural Gas Genset, SOFC Fuel Cell, PEM Fuel Cell (H\u2082), or Rotary UPS + Flywheel. Each has different footprint, emissions, and unit sizing.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets4", level: 0 },
          children: [new TextRun({ text: "Cooling Factor Override: ", bold: true }), new TextRun("Optionally override the default m\u00B2/kW factor for cooling equipment area calculation.")],
        }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Results show: total ground/roof area needed, utilization ratios, whether equipment fits (green/red badges), number of backup units, and a detailed element-by-element breakdown table with sizing basis, area factor, and source citation for each piece of equipment.")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Backup Power Comparison")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "Click \"Compare\" to see all five backup power technologies side by side. The comparison table shows unit count, unit size (kW), annual CO\u2082 emissions (tonnes/year), and physical footprint (m\u00B2) for each technology. Summary highlights identify the lowest CO\u2082, smallest footprint, and fastest ramp-up technologies."
          )],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 6. TAB 4: SENSITIVITY
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("6. Tab 4: Sensitivity")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The Sensitivity tab helps answer \"what if\" questions about how changes in key parameters affect IT capacity."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Tornado Chart (\u00B110% Sensitivity)")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Click \"Compute\" to generate a tornado diagram. The engine varies each input parameter by \u00B110% from its current value (one at a time, holding others constant) and measures the impact on IT load output. Parameters analyzed include:")],
        }),
        new Paragraph({
          numbering: { reference: "bullets5", level: 0 },
          children: [new TextRun("PUE (Power Usage Effectiveness)")],
        }),
        new Paragraph({
          numbering: { reference: "bullets5", level: 0 },
          children: [new TextRun("Eta Chain (power distribution efficiency)")],
        }),
        new Paragraph({
          numbering: { reference: "bullets5", level: 0 },
          children: [new TextRun("Rack Density (kW per rack)")],
        }),
        new Paragraph({
          numbering: { reference: "bullets5", level: 0 },
          children: [new TextRun("Whitespace Ratio, Site Coverage Ratio")],
        }),
        new Paragraph({
          numbering: { reference: "bullets5", level: 0 },
          children: [new TextRun("Available Power (MW), Land Area, Number of Floors")],
        }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("The chart ranks parameters by impact magnitude. Wider bars indicate parameters that have the greatest effect on output. This identifies which assumptions or design choices matter most for your site.")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Break-Even Solver")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "Enter a target IT load (MW) and select a parameter to solve for. The engine uses bisection to find the exact parameter value needed to achieve your target. For example: \"What PUE would I need to reach 15 MW IT?\" or \"How much available power do I need for 20 MW IT?\" The solver reports whether the target is feasible, the required parameter value, and the percentage change from baseline."
          )],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 7. TAB 5: EXPANSION
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("7. Tab 5: Expansion")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The Expansion tab assesses future growth potential and includes a load mix optimization tool. This is advisory only \u2014 expansion results do not change the main scenario score."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Expansion Advisory")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Click \"Compute\" to analyze three capacity tiers:")],
        }),
        new Paragraph({
          numbering: { reference: "bullets6", level: 0 },
          children: [new TextRun({ text: "Current Feasible: ", bold: true }), new TextRun("What the site can deliver today with active floors and current grid connection.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets6", level: 0 },
          children: [new TextRun({ text: "Future Expandable: ", bold: true }), new TextRun("Additional capacity from reserved expansion floors (declared by the user in Site Manager) and any latent height-based floors (calculated from max building height minus active floors).")],
        }),
        new Paragraph({
          numbering: { reference: "bullets6", level: 0 },
          children: [new TextRun({ text: "Total Site Potential: ", bold: true }), new TextRun("Sum of current + future, representing the theoretical maximum if all floors are built out and additional grid capacity is secured.")],
        }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Key metrics include: active floors, reserved/height-uplift floors, max total floors, unused active racks, expansion racks, total additional racks, current facility/procurement envelope, extra grid request needed, and the binding constraint. Engineering notes flag important considerations such as structural limits or grid application requirements.")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Load Mix Planner")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun(
            "The Load Mix Planner explores blended workload allocations within a single IT envelope. For example, you might want to know the optimal split between HPC, colocation, and AI/GPU workloads given your site\u2019s cooling topology and total IT power."
          )],
        }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Inputs (pre-filled from the selected scenario):")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Total IT (MW): ", bold: true }), new TextRun("The total IT power envelope to allocate across load types.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Cooling Type: ", bold: true }), new TextRun("The cooling topology (determines compatibility with each load type).")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Density Scenario: ", bold: true }), new TextRun("Low, typical, or high rack density.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Step %: ", bold: true }), new TextRun("Granularity of share combinations (e.g., 10% = 0%, 10%, 20%... 100%).")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Min Racks: ", bold: true }), new TextRun("Minimum rack count per load type to be included in a candidate.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Top N: ", bold: true }), new TextRun("Number of top-ranked candidates to display.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets7", level: 0 },
          children: [new TextRun({ text: "Allowed Load Types: ", bold: true }), new TextRun("Select at least two load types to blend.")],
        }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun("The optimizer evaluates all deterministic share combinations that sum to 100%, ranks them by a composite score (considering blended PUE, total racks, and compatibility), and displays the top candidates. Each candidate shows its allocation table, compatibility status, and trade-off notes.")],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 8. TAB 6: FIRM CAPACITY
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("8. Tab 6: Firm Capacity")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "The Firm Capacity tab answers: \"With this site\u2019s fixed grid limit, what constant IT load can I guarantee all year?\" It requires hourly weather simulation and models peak-support assets that fill the hottest-hour cooling deficits."
          )],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Support Asset Inputs")] }),
        new Paragraph({
          numbering: { reference: "bullets8", level: 0 },
          children: [new TextRun({ text: "BESS (kWh): ", bold: true }), new TextRun("Battery Energy Storage System capacity. Used to time-shift grid power: charges during cool hours, discharges during hot hours when cooling demand spikes.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets8", level: 0 },
          children: [new TextRun({ text: "Fuel Cell (kW): ", bold: true }), new TextRun("On-site fuel cell generation capacity. Provides continuous supplemental power during peak periods.")],
        }),
        new Paragraph({
          numbering: { reference: "bullets8", level: 0 },
          children: [new TextRun({ text: "Backup Dispatch (kW): ", bold: true }), new TextRun("Diesel/gas generator dispatch for peak shaving (separate from N+1 backup; this is active load support).")],
        }),
        new Paragraph({
          numbering: { reference: "bullets8", level: 0 },
          children: [new TextRun({ text: "Target IT (MW): ", bold: true }), new TextRun("Optional. If set, the engine evaluates whether this specific target is achievable with the given support assets.")],
        }),

        new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun("Output Metrics")] }),
        new Paragraph({
          spacing: { after: 100 },
          children: [new TextRun("Results are split into baseline (grid-only) and supported (with assets) sections:")],
        }),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3000, 6360],
          rows: [
            new TableRow({ children: [headerCell("Metric", 3000), headerCell("Description", 6360)] }),
            new TableRow({ children: [cell("Nominal IT", 3000, { bold: true }), cell("Static-model IT load (no hourly variation)", 6360)] }),
            new TableRow({ children: [cell("Grid-Only Worst", 3000, { bold: true, shade: true }), cell("Minimum IT capacity without any support assets", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Grid-Only P99", 3000, { bold: true }), cell("IT capacity achievable 99% of hours without support", 6360)] }),
            new TableRow({ children: [cell("Supported Firm IT", 3000, { bold: true, shade: true }), cell("Maximum constant IT load achievable with support assets filling deficits", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Gain vs Worst", 3000, { bold: true }), cell("MW improvement over grid-only worst hour", 6360)] }),
            new TableRow({ children: [cell("Gain vs P99", 3000, { bold: true, shade: true }), cell("MW improvement over grid-only P99", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Peak Support", 3000, { bold: true }), cell("Maximum simultaneous support power needed", 6360)] }),
            new TableRow({ children: [cell("Hours Above Grid Cap", 3000, { bold: true, shade: true }), cell("Number of hours where facility demand exceeds grid capacity", 6360, { shade: true })] }),
            new TableRow({ children: [cell("BESS Cycle State", 3000, { bold: true }), cell("Whether the cyclic year solve converged (BESS returns to starting state)", 6360)] }),
          ],
        }),

        new Paragraph({ spacing: { before: 200, after: 200 }, children: [new TextRun(
          "The system also provides recommended compensation packages: pre-configured asset combinations designed to bridge the gap between P99 and worst-hour IT capacity. Each recommendation shows its BESS, fuel cell, and backup sizing, feasibility status, and dispatch breakdown."
        )] }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 9. SCORING SYSTEM
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("9. Scoring System")] }),
        new Paragraph({
          spacing: { after: 200 },
          children: [new TextRun(
            "Every scenario receives a composite feasibility score from 0 to 100. The score is computed by the backend engine using weighted factors:"
          )],
        }),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3200, 1600, 4560],
          rows: [
            new TableRow({ children: [headerCell("Factor", 3200), headerCell("Weight", 1600), headerCell("Description", 4560)] }),
            new TableRow({ children: [cell("PUE Efficiency", 3200), cell("25%", 1600), cell("Lower PUE = better score. Normalized against reference range.", 4560)] }),
            new TableRow({ children: [cell("IT Capacity", 3200, { shade: true }), cell("25%", 1600, { shade: true }), cell("Higher IT capacity relative to best scenario in batch = better score.", 4560, { shade: true })] }),
            new TableRow({ children: [cell("Rack Deployment Ratio", 3200), cell("15%", 1600), cell("Racks deployed vs effective racks possible. Higher utilization = better.", 4560)] }),
            new TableRow({ children: [cell("RAG Status", 3200, { shade: true }), cell("20%", 1600, { shade: true }), cell("BLUE=100%, GREEN=75%, AMBER=40%, RED=0%.", 4560, { shade: true })] }),
            new TableRow({ children: [cell("Ground Utilization", 3200), cell("10%", 1600), cell("Ground equipment area vs available outdoor area. Moderate utilization preferred.", 4560)] }),
            new TableRow({ children: [cell("Roof Utilization", 3200, { shade: true }), cell("5%", 1600, { shade: true }), cell("Roof equipment area vs available roof area.", 4560, { shade: true })] }),
          ],
        }),

        new Paragraph({ children: [new PageBreak()] }),

        // ═══════════════════════════════════════════
        // 10. GLOSSARY
        // ═══════════════════════════════════════════
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("10. Glossary")] }),
        new Table({
          width: { size: 9360, type: WidthType.DXA },
          columnWidths: [3000, 6360],
          rows: [
            new TableRow({ children: [headerCell("Term", 3000), headerCell("Definition", 6360)] }),
            new TableRow({ children: [cell("PUE", 3000, { bold: true }), cell("Power Usage Effectiveness. Total facility power / IT equipment power. Ideal = 1.0.", 6360)] }),
            new TableRow({ children: [cell("P99", 3000, { bold: true, shade: true }), cell("The 99th percentile value from 8,760 hourly simulations. 1% of hours may fall below this.", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Eta Chain", 3000, { bold: true }), cell("Power distribution chain efficiency (transformer, UPS, PDU losses). Typically 0.85\u20130.95.", 6360)] }),
            new TableRow({ children: [cell("BESS", 3000, { bold: true, shade: true }), cell("Battery Energy Storage System. Stores and releases electrical energy for peak shaving.", 6360, { shade: true })] }),
            new TableRow({ children: [cell("DLC", 3000, { bold: true }), cell("Direct Liquid Cooling. Coolant flows directly to server components. Best PUE for high-density.", 6360)] }),
            new TableRow({ children: [cell("RDHx", 3000, { bold: true, shade: true }), cell("Rear Door Heat Exchanger. Water-cooled door on the back of each rack.", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Economizer", 3000, { bold: true }), cell("Free cooling using outside air when ambient temperature is low enough.", 6360)] }),
            new TableRow({ children: [cell("Whitespace", 3000, { bold: true, shade: true }), cell("The portion of each floor dedicated to IT racks (vs corridors, mechanical rooms).", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Procurement Factor", 3000, { bold: true }), cell("Safety multiplier on grid capacity request (typically 1.1\u20131.15).", 6360)] }),
            new TableRow({ children: [cell("Binding Constraint", 3000, { bold: true, shade: true }), cell("Whether site capacity is limited by POWER (grid) or SPACE (physical footprint).", 6360, { shade: true })] }),
            new TableRow({ children: [cell("Tornado Chart", 3000, { bold: true }), cell("Horizontal bar chart showing which input parameters most affect the output.", 6360)] }),
            new TableRow({ children: [cell("Firm Capacity", 3000, { bold: true, shade: true }), cell("The constant IT load guaranteed 100% of hours with support asset compensation.", 6360, { shade: true })] }),
          ],
        }),
      ],
    },
  ],
});

const OUTPUT = "/Users/mostafashami/Desktop/dc-feasibility-v4/docs/Results_Dashboard_Features.docx";
Packer.toBuffer(doc).then((buffer) => {
  fs.writeFileSync(OUTPUT, buffer);
  console.log("Created:", OUTPUT);
});
