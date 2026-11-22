import { configSchematics } from "./config.js";
import { generate } from "./generator.js";

// The single generator selected in LM Studio is the front door to all seven
// OpenClaw agents. No model-delegated tool provider can bypass approvals.
export async function main(context) {
  context.withConfigSchematics(configSchematics);
  context.withGenerator(generate);
}
