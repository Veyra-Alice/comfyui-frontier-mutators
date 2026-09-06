import { app } from "../../scripts/app.js";


const MUTATOR_NODES = new Set([
  "FrontierFloatMutator",
  "FrontierIntegerMutator",
]);


function first(message, name, fallback = "-") {
  const value = message?.[name];
  if (Array.isArray(value)) return value[0] ?? fallback;
  return value ?? fallback;
}


app.registerExtension({
  name: "Veyra.FrontierMutators",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!MUTATOR_NODES.has(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);

      this.frontierLastSample = null;
      this.frontierReadout = this.addWidget(
        "text",
        "last sample",
        "not run",
        () => {},
        { serialize: false }
      );
      this.frontierReadout.disabled = true;

      this.addWidget("button", "Commit sampled value", null, () => {
        if (this.frontierLastSample === null) return;

        const centre = this.widgets?.find((widget) => widget.name === "centre");
        const distribution = this.widgets?.find(
          (widget) => widget.name === "distribution"
        );
        const lock = this.widgets?.find(
          (widget) => widget.name === "lock_current"
        );

        if (centre) centre.value = this.frontierLastSample;
        if (distribution) distribution.value = "fixed";
        if (lock) lock.value = true;
        this.graph?.setDirtyCanvas(true, true);
      });

      const size = this.computeSize();
      this.setSize([Math.max(this.size[0], 300), Math.max(this.size[1], size[1])]);
      return result;
    };

    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);

      const sampleText = String(first(message, "sample"));
      const seedText = String(first(message, "effective_seed"));
      const lockText = String(first(message, "locked"));
      const centre = this.widgets?.find((widget) => widget.name === "centre");

      this.frontierLastSample =
        nodeData.name === "FrontierIntegerMutator"
          ? Number.parseInt(sampleText, 10)
          : Number.parseFloat(sampleText);

      if (this.frontierReadout) {
        this.frontierReadout.value = `${sampleText} | seed ${seedText} | ${lockText}`;
      }
      if (centre && Number.isNaN(this.frontierLastSample)) {
        this.frontierLastSample = centre.value;
      }
      this.graph?.setDirtyCanvas(true, true);
    };
  },
});
