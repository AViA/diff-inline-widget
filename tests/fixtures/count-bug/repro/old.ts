
  private render(): void {
    const report = this.report;
    byId("out").hidden = !report;
    if (!report || !this.engine) return;
    const engine = this.engine;
    const count = (s: Status): number => report.entries.filter((e) => e.status === s).length;
    byId("sum").innerHTML =
      `${report.activeGroups} groups considered. <b>${report.entries.length}</b> items: <b class="m">${count("safe")}</b> safe to discard, ` +
      `<b class="tag">${count("review")}</b> to review, <b>${count("keep")}</b> keep.` +
      (report.listFilterIgnored ? ` <span class="why">(“For listed members only” is ignored: this file lists no members.)</span>` : "");
