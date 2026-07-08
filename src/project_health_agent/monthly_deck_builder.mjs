import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const [dataPath, outputPptx, previewDir, qaDir, inspectPath] = process.argv.slice(2);

if (!dataPath || !outputPptx || !previewDir || !qaDir || !inspectPath) {
  console.error(
    "Usage: node monthly_deck_builder.mjs <data-json> <output-pptx> <preview-dir> <qa-dir> <inspect-path>",
  );
  process.exit(1);
}

const COLORS = {
  canvas: "#FFFFFF",
  ink: "#111111",
  muted: "#5F6368",
  panel: "#F1F3F4",
  line: "#C8CDD2",
  accent: "#D9481C",
  accentSoft: "#FDE9E2",
};

function metricCard(slide, x, y, w, h, value, label, fill = COLORS.panel, valueColor = COLORS.ink) {
  slide.shapes.add({
    geometry: "rect",
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: fill, width: 0 },
  });

  const valueBox = slide.shapes.add({
    geometry: "textbox",
    position: { left: x + 18, top: y + 18, width: w - 36, height: 54 },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  valueBox.text = value;
  valueBox.text.style = { fontSize: 34, bold: true, color: valueColor };

  const labelBox = slide.shapes.add({
    geometry: "textbox",
    position: { left: x + 18, top: y + 82, width: w - 36, height: h - 96 },
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  labelBox.text = label;
  labelBox.text.style = { fontSize: 18, color: COLORS.muted };
}

function addText(slide, text, position, style) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = style;
  return shape;
}

function addRule(slide, left, top, width, fill = COLORS.line, height = 2) {
  slide.shapes.add({
    geometry: "rect",
    position: { left, top, width, height },
    fill,
    line: { style: "solid", fill, width: 0 },
  });
}

function addSlideNumber(slide, number) {
  addText(
    slide,
    String(number).padStart(2, "0"),
    { left: 1184, top: 666, width: 48, height: 20 },
    { fontSize: 15, color: COLORS.muted, alignment: "right" },
  );
}

function addTitle(slide, title, subtitle = "") {
  addText(
    slide,
    title,
    { left: 48, top: 34, width: 880, height: 56 },
    { fontSize: 38, bold: true, color: COLORS.ink },
  );
  if (subtitle) {
    addText(
      slide,
      subtitle,
      { left: 48, top: 92, width: 980, height: 44 },
      { fontSize: 20, color: COLORS.muted },
    );
  }
}

function shortReason(text) {
  return String(text || "").replace(/\.$/, "");
}

function orderedDrivers(data) {
  return Object.entries(data.overall.lead_driver_counts || {}).sort((left, right) => right[1] - left[1]);
}

function compactProjectName(name) {
  return String(name || "")
    .replace(/^Zycus - /i, "")
    .replace(/\s+Implementation$/i, " implementation");
}

function buildExecutiveSummary(slide, data) {
  slide.background.fill = COLORS.canvas;
  addTitle(
    slide,
    "Executive Summary",
    "Automated monthly client-ready view generated from the analyzed project plans.",
  );
  const drivers = orderedDrivers(data);
  const leadDriver = drivers[0]?.[0] || "Schedule";
  const secondDriver = drivers[1]?.[0] || "Execution";
  const focusProject = compactProjectName(
    data.plan_b?.project_name || data.critical_projects?.[0]?.project_name || "the highest-risk project",
  );

  metricCard(slide, 48, 156, 270, 150, String(data.overall.project_count), "Projects");
  metricCard(slide, 336, 156, 270, 150, String(data.overall.rag_counts.Green || 0), "Green", COLORS.accentSoft);
  metricCard(slide, 624, 156, 270, 150, String(data.overall.rag_counts.Amber || 0), "Amber");
  metricCard(slide, 912, 156, 270, 150, String(data.overall.rag_counts.Red || 0), "Red", "#F8D7CC", COLORS.accent);

  addRule(slide, 48, 348, 180, COLORS.ink, 3);
  addText(
    slide,
    `${data.overall.red_pct}% of analyzed views are currently red, which indicates that schedule recovery and execution control need executive attention before the next client reporting cycle.`,
    { left: 48, top: 372, width: 760, height: 110 },
    { fontSize: 24, color: COLORS.ink },
  );

  slide.shapes.add({
    geometry: "rect",
    position: { left: 846, top: 354, width: 336, height: 310 },
    fill: COLORS.panel,
    line: { style: "solid", fill: COLORS.panel, width: 0 },
  });
  addText(
    slide,
    "This month at a glance",
    { left: 872, top: 382, width: 280, height: 28 },
    { fontSize: 22, bold: true, color: COLORS.ink },
  );
  addText(
    slide,
    `${leadDriver} is the most common lead driver.\n\n${secondDriver} pressure is the next-most common concern across the current plans.\n\n${focusProject} remains red and should stay on the next escalation review list.`,
    { left: 872, top: 426, width: 270, height: 214 },
    { fontSize: 18, color: COLORS.ink },
  );

  addSlideNumber(slide, 1);
}

function buildPortfolioHealth(slide, data) {
  slide.background.fill = COLORS.canvas;
  addTitle(
    slide,
    "Portfolio Health",
    "RAG distribution, average score, and model validation point to a portfolio that is broadly under delivery pressure.",
  );
  const validationAccuracy = data.portfolio.validation_accuracy;
  const validationLabel = validationAccuracy == null ? "N/A" : `${Math.round(validationAccuracy * 100)}%`;
  const validationNarrative =
    validationAccuracy == null
      ? "The original workbooks did not provide enough benchmark labels to calculate a validation accuracy figure."
      : `Validation against the embedded workbook health labels holds at ${Math.round(validationAccuracy * 100)}%, which is directionally useful for leadership screening while keeping the reasoning transparent.`;

  slide.shapes.add({
    geometry: "rect",
    position: { left: 48, top: 154, width: 620, height: 474 },
    fill: COLORS.panel,
    line: { style: "solid", fill: COLORS.panel, width: 0 },
  });
  addText(
    slide,
    "RAG Distribution",
    { left: 76, top: 176, width: 220, height: 28 },
    { fontSize: 22, bold: true, color: COLORS.ink },
  );
  metricCard(slide, 92, 244, 156, 190, String(data.overall.rag_counts.Green || 0), "Green");
  metricCard(slide, 278, 244, 156, 190, String(data.overall.rag_counts.Amber || 0), "Amber");
  metricCard(slide, 464, 244, 156, 190, String(data.overall.rag_counts.Red || 0), "Red", COLORS.accentSoft, COLORS.accent);
  addText(
    slide,
    `${data.overall.project_count} project plans were analyzed in this run, and every current view is red or amber-weighted enough to need active leadership attention.`,
    { left: 92, top: 470, width: 528, height: 84 },
    { fontSize: 20, color: COLORS.ink },
  );

  metricCard(
    slide,
    716,
    170,
    232,
    154,
    `${data.overall.average_score}/100`,
    "Overall Score",
  );
  metricCard(
    slide,
    966,
    170,
    216,
    154,
    validationLabel,
    "Validation Accuracy",
    COLORS.accentSoft,
    COLORS.accent,
  );

  addText(
    slide,
    `The average score across all ${data.overall.project_count} analyzed project plans is ${data.overall.average_score}/100. ${validationNarrative}`,
    { left: 716, top: 374, width: 466, height: 176 },
    { fontSize: 21, color: COLORS.ink },
  );

  addSlideNumber(slide, 2);
}

function buildEmergingRisks(slide, data) {
  slide.background.fill = COLORS.canvas;
  addTitle(
    slide,
    "Emerging Risks",
    "Delay, budget burn, staffing pressure, and stakeholder confidence are emerging together rather than as isolated signals.",
  );

  metricCard(
    slide,
    48,
    164,
    268,
    170,
    String(data.portfolio.burn_ahead_gt_10pts || 0),
    "Budget Burn",
  );
  metricCard(
    slide,
    332,
    164,
    268,
    170,
    String(data.portfolio.delay_gt_14_days || 0),
    "Schedule Delays",
    COLORS.accentSoft,
    COLORS.accent,
  );
  metricCard(
    slide,
    48,
    352,
    268,
    170,
    String(data.portfolio.resource_util_gt_90 || 0),
    "Resource Issues",
  );
  metricCard(
    slide,
    332,
    352,
    268,
    170,
    String(data.portfolio.negative_or_neutral_sentiment || 0),
    "Stakeholder Concerns",
  );

  slide.shapes.add({
    geometry: "rect",
    position: { left: 644, top: 164, width: 538, height: 358 },
    fill: COLORS.panel,
    line: { style: "solid", fill: COLORS.panel, width: 0 },
  });
  addText(
    slide,
    "Risk interpretation",
    { left: 674, top: 192, width: 220, height: 28 },
    { fontSize: 24, bold: true, color: COLORS.ink },
  );
  addText(
    slide,
    `${data.portfolio.delay_gt_14_days || 0} projects are already more than two weeks behind, and ${data.portfolio.burn_ahead_gt_10pts || 0} are spending ahead of delivery progress.\n\n${data.portfolio.critical_blocker_projects || 0} projects also carry two or more critical blockers, which means the schedule risk is likely to stay elevated unless escalation gets faster.\n\nResource utilization above 90% and neutral or negative stakeholder sentiment show that the pressure is visible both inside the delivery teams and with client-facing sponsors.`,
    { left: 674, top: 238, width: 456, height: 232 },
    { fontSize: 20, color: COLORS.ink },
  );

  addSlideNumber(slide, 3);
}

function buildCriticalProjects(slide, data) {
  slide.background.fill = COLORS.canvas;
  addTitle(
    slide,
    "Critical Projects",
    "Top five red projects by score, ranked by the severity of the current delivery signal.",
  );

  const criticalProjects = data.critical_projects || [];
  const table = slide.tables.add({
    rows: criticalProjects.length + 1,
    columns: 3,
    left: 48,
    top: 166,
    width: 1134,
    height: 420,
    values: [
      ["Project", "Score", "Reason"],
      ...criticalProjects.map((item) => [
        item.project_name,
        String(item.overall_score),
        shortReason(item.reason_1),
      ]),
    ],
    columnWidths: [320, 110, 704],
  });
  table.styleOptions = { headerRow: true, bandedRows: true };
  table.borders.assign({ style: "solid", fill: COLORS.line, width: 1 });
  for (let col = 0; col < 3; col += 1) {
    table.getCell(0, col).fill = COLORS.panel;
    table.getCell(0, col).text.style = { fontSize: 15, bold: true, color: COLORS.ink };
  }
  table.cells.block({ row: 1, column: 0, rowCount: criticalProjects.length, columnCount: 3 }).assign({
    textStyle: { fontSize: 13, color: COLORS.ink },
  });

  addText(
    slide,
    "These projects should be reviewed first in the next escalation cadence because they combine the highest risk scores with clear delivery explanations.",
    { left: 48, top: 608, width: 980, height: 42 },
    { fontSize: 20, color: COLORS.ink },
  );

  addSlideNumber(slide, 4);
}

function buildRecommendations(slide) {
  slide.background.fill = COLORS.canvas;
  addTitle(
    slide,
    "Recommendations",
    "The next operating cycle should focus on recovery discipline, blocker escalation, and cleaner execution reporting.",
  );

  const actions = [
    {
      number: "01",
      title: "Increase staffing where utilization is already above safe limits",
      body: "Reassign or add capacity to the most constrained plans before schedule recovery work pushes the same teams further behind.",
    },
    {
      number: "02",
      title: "Escalate blocked projects through a daily unblock cadence",
      body: "Use a standing review for critical blockers and P1 issues so execution stalls do not sit inside weekly status reports.",
    },
    {
      number: "03",
      title: "Rebaseline delayed milestones and enforce dated recovery plans",
      body: "Reset dates at milestone level for the top red projects and review burn-versus-progress weekly until the gap narrows.",
    },
  ];

  actions.forEach((action, index) => {
    const top = 164 + index * 154;
    slide.shapes.add({
      geometry: "rect",
      position: { left: 48, top, width: 1134, height: 126 },
      fill: index === 0 ? COLORS.accentSoft : COLORS.panel,
      line: { style: "solid", fill: index === 0 ? COLORS.accentSoft : COLORS.panel, width: 0 },
    });
    addText(
      slide,
      action.number,
      { left: 78, top: top + 36, width: 62, height: 32 },
      { fontSize: 24, bold: true, color: COLORS.accent },
    );
    addText(
      slide,
      action.title,
      { left: 164, top: top + 24, width: 920, height: 30 },
      { fontSize: 22, bold: true, color: COLORS.ink },
    );
    addText(
      slide,
      action.body,
      { left: 164, top: top + 62, width: 910, height: 40 },
      { fontSize: 18, color: COLORS.ink },
    );
  });

  addSlideNumber(slide, 5);
}

function buildOutlook(slide, data) {
  slide.background.fill = COLORS.canvas;
  addTitle(
    slide,
    "Next Month Outlook",
    "The near-term forecast improves only if the current red watchlist receives faster recovery actions than it did this month.",
  );

  slide.shapes.add({
    geometry: "rect",
    position: { left: 48, top: 168, width: 492, height: 332 },
    fill: COLORS.panel,
    line: { style: "solid", fill: COLORS.panel, width: 0 },
  });
  addText(
    slide,
    "Forecast",
    { left: 76, top: 198, width: 180, height: 28 },
    { fontSize: 24, bold: true, color: COLORS.ink },
  );
  addText(
    slide,
    data.outlook.forecast,
    { left: 76, top: 246, width: 418, height: 188 },
    { fontSize: 22, color: COLORS.ink },
  );

  slide.shapes.add({
    geometry: "rect",
    position: { left: 578, top: 168, width: 604, height: 332 },
    fill: COLORS.accentSoft,
    line: { style: "solid", fill: COLORS.accentSoft, width: 0 },
  });
  addText(
    slide,
    "Expected improvements",
    { left: 606, top: 198, width: 380, height: 32 },
    { fontSize: 22, bold: true, color: COLORS.ink },
  );
  addText(
    slide,
    `1. ${data.outlook.expected_improvements[0]}\n\n2. ${data.outlook.expected_improvements[1]}\n\n3. ${data.outlook.expected_improvements[2]}`,
    { left: 606, top: 254, width: 520, height: 204 },
    { fontSize: 18, color: COLORS.ink },
  );

  addText(
    slide,
    `Project Plan B should stay on the watchlist next month because it remains ${data.plan_b.rag_status} and still carries a ${Math.round(data.plan_b.progress_signal_gap || 0)}-point gap between weekly and task-level progress.`,
    { left: 48, top: 560, width: 1134, height: 56 },
    { fontSize: 21, color: COLORS.ink },
  );

  addSlideNumber(slide, 6);
}

async function writeBlob(path, blob) {
  await fs.writeFile(path, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  const data = JSON.parse(await fs.readFile(dataPath, "utf8"));
  await fs.mkdir(previewDir, { recursive: true });
  await fs.mkdir(qaDir, { recursive: true });

  const presentation = Presentation.create({
    slideSize: { width: 1280, height: 720 },
  });

  buildExecutiveSummary(presentation.slides.add(), data);
  buildPortfolioHealth(presentation.slides.add(), data);
  buildEmergingRisks(presentation.slides.add(), data);
  buildCriticalProjects(presentation.slides.add(), data);
  buildRecommendations(presentation.slides.add(), data);
  buildOutlook(presentation.slides.add(), data);

  for (const [index, slide] of presentation.slides.items.entries()) {
    const png = await presentation.export({ slide, format: "png", scale: 1 });
    await writeBlob(`${previewDir}/slide-${String(index + 1).padStart(2, "0")}.png`, png);
  }

  const montage = await presentation.export({
    format: "webp",
    montage: true,
    scale: 1,
  });
  await writeBlob(`${qaDir}/deck-montage.webp`, montage);

  const inspect = await presentation.inspect({
    kind: "slide,textbox,shape,table,chart",
    maxChars: 24000,
  });
  await fs.writeFile(inspectPath, inspect.ndjson, "utf8");

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(outputPptx);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});