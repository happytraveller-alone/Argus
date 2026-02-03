import type { DomDictionary } from "./types";
import { commonDictionary } from "./common";
import { agentAuditDictionary } from "./agentAudit";
import { dashboardDictionary } from "./dashboard";
import { projectsDictionary } from "./projects";
import { opengrepRulesDictionary } from "./opengrepRules";
import { systemConfigDictionary } from "./systemConfig";
import { intelligentAuditDictionary } from "./intelligentAudit";

export const manualDomTranslations: DomDictionary = {
  ...commonDictionary,
  ...agentAuditDictionary,
  ...dashboardDictionary,
  ...projectsDictionary,
  ...opengrepRulesDictionary,
  ...systemConfigDictionary,
  ...intelligentAuditDictionary,
};
