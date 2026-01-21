import { FlatAgent, type MachineHooks, type AgentConfig } from 'flatagents';
import { createInterface } from 'readline/promises';
import { stdin as input, stdout as output } from 'process';
import { join } from 'path';

type Metrics = {
  agents_generated: number;
  agents_executed: number;
  supervisor_rejections: number;
  human_denials: number;
};

export class OTFAgentHooks implements MachineHooks {
  private metrics: Metrics = {
    agents_generated: 0,
    agents_executed: 0,
    supervisor_rejections: 0,
    human_denials: 0,
  };
  private configDir: string;
  private profilesFile: string;

  constructor(configDir: string) {
    this.configDir = configDir;
    this.profilesFile = join(configDir, 'profiles.yml');
  }

  async onAction(action: string, context: Record<string, any>): Promise<Record<string, any>> {
    if (action === 'human_review_otf') {
      return this.humanReviewOtf(context);
    }
    if (action === 'otf_execute') {
      return this.otfExecute(context);
    }
    return context;
  }

  getMetrics(): Metrics {
    return { ...this.metrics };
  }

  private async prompt(question: string): Promise<string> {
    const rl = createInterface({ input, output });
    const answer = await rl.question(question);
    rl.close();
    return answer.trim();
  }

  private async humanReviewOtf(context: Record<string, any>): Promise<Record<string, any>> {
    console.log(`\n${'='.repeat(70)}`);
    console.log('OTF AGENT REVIEW');
    console.log('='.repeat(70));

    console.log('\n📋 ORIGINAL TASK:');
    console.log(`   ${context.task ?? '(unknown)'}`);

    const name = context.otf_name ?? 'unnamed';
    const system = context.otf_system ?? '(none)';
    const user = context.otf_user ?? '(none)';
    const temperature = context.otf_temperature ?? 'N/A';

    console.log(`\n🤖 GENERATED AGENT: ${name}`);
    console.log('-'.repeat(50));
    console.log(`Temperature: ${temperature}`);
    const systemText = system ? String(system) : '(none)';
    console.log(`\nSystem Prompt:\n${systemText}`);
    const taskText = context.task ? String(context.task) : '';
    const userText = user ? String(user) : '(none)';
    const userRendered = userText
      .replace(/<<\s*input\.task\s*>>/g, taskText)
      .replace(/\{\{\s*input\.task\s*\}\}/g, taskText);
    console.log(`\nUser Prompt Template:\n${userRendered}`);

    console.log(`\n${'-'.repeat(50)}`);
    const supervisorApproved = Boolean(context.supervisor_approved);

    if (supervisorApproved) {
      console.log('✅ SUPERVISOR APPROVED');
    } else {
      console.log('❌ SUPERVISOR REJECTED');
      this.metrics.supervisor_rejections += 1;
    }

    console.log(`\n📊 ANALYSIS:\n${context.supervisor_analysis ?? '(none)'}`);
    if (context.supervisor_concerns) {
      console.log(`\n⚠️  CONCERNS:\n${context.supervisor_concerns}`);
    }

    console.log('-'.repeat(50));

    if (supervisorApproved) {
      console.log('\nThe supervisor approved this agent.');
      const response = await this.prompt('Your decision: [a]pprove / [d]eny / [q]uit: ');
      const normalized = response.toLowerCase();

      if (normalized === '' || normalized === 'a' || normalized === 'approve') {
        context.human_approved = true;
        context.human_acknowledged = true;
        console.log('✓ Approved! Agent will be executed.');
      } else if (normalized === 'q' || normalized === 'quit') {
        throw new Error('Execution cancelled by user.');
      } else {
        context.human_approved = false;
        context.human_acknowledged = true;
        this.metrics.human_denials += 1;
        console.log('✗ Denied. Will regenerate agent.');
      }
    } else {
      console.log('\nThe supervisor rejected this agent. You can only acknowledge.');
      const response = await this.prompt('Press Enter to acknowledge and regenerate, or "q" to quit: ');
      const normalized = response.toLowerCase();

      if (normalized === 'q' || normalized === 'quit') {
        throw new Error('Execution cancelled by user.');
      }

      context.human_approved = false;
      context.human_acknowledged = true;
      console.log('→ Acknowledged. Will regenerate agent with feedback.');
    }

    console.log(`${'='.repeat(70)}\n`);
    return context;
  }

  private async otfExecute(context: Record<string, any>): Promise<Record<string, any>> {
    const name = context.otf_name ?? 'otf-agent';
    const system = context.otf_system ?? 'You are a helpful creative writer.';
    const user = context.otf_user ?? '{{ input.task }}';
    const temperatureRaw = context.otf_temperature ?? 0.6;
    const outputFieldsRaw = context.otf_output_fields ?? '{}';

    console.log(`\n${'='.repeat(70)}`);
    console.log(`🚀 EXECUTING OTF AGENT: ${name}`);
    console.log('='.repeat(70));

    let outputFields: Record<string, any> = {};
    if (typeof outputFieldsRaw === 'string') {
      try {
        outputFields = JSON.parse(outputFieldsRaw);
      } catch {
        outputFields = {};
      }
    } else if (typeof outputFieldsRaw === 'object' && outputFieldsRaw) {
      outputFields = outputFieldsRaw as Record<string, any>;
    }

    const outputSchema: Record<string, any> = {};
    if (outputFields && typeof outputFields === 'object') {
      for (const [fieldName, fieldDef] of Object.entries(outputFields)) {
        if (fieldDef && typeof fieldDef === 'object') {
          outputSchema[fieldName] = fieldDef;
        } else {
          outputSchema[fieldName] = { type: 'str', description: String(fieldDef) };
        }
      }
    }

    if (!Object.keys(outputSchema).length) {
      outputSchema.content = { type: 'str', description: 'The creative writing output' };
    }

    let temperature = typeof temperatureRaw === 'string' ? Number(temperatureRaw) : Number(temperatureRaw);
    if (!Number.isFinite(temperature)) {
      temperature = 0.6;
    }
    if (temperature !== 1.0) {
      temperature = 0.6;
    }

    const profileName = temperature === 0.6 ? 'creative' : 'default';

    const normalizedUser = String(user)
      .replace(/<<\s*input\.task\s*>>/g, '{{ input.task }}')
      .trim();

    const agentConfig: AgentConfig = {
      spec: 'flatagent',
      spec_version: '0.7.7',
      data: {
        name,
        model: profileName,
        system: String(system),
        user: normalizedUser,
        output: outputSchema,
      },
    };

    try {
      const agent = new FlatAgent({
        config: agentConfig,
        configDir: this.configDir,
        profilesFile: this.profilesFile,
      });
      this.metrics.agents_generated += 1;

      const result = await agent.call({ task: context.task ?? '' });
      this.metrics.agents_executed += 1;

      if (result.output) {
        context.otf_result = result.output;
      } else if (result.content) {
        context.otf_result = { content: result.content };
      } else {
        context.otf_result = { content: '(empty response)' };
      }

      console.log('\n📝 OUTPUT:');
      console.log('-'.repeat(50));
      if (typeof context.otf_result === 'object' && context.otf_result) {
        for (const [key, value] of Object.entries(context.otf_result)) {
          console.log(`${key}: ${value}`);
        }
      } else {
        console.log(context.otf_result);
      }
      console.log('-'.repeat(50));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      context.otf_result = { error: message };
      console.log(`\n❌ Error: ${message}`);
    }

    console.log(`${'='.repeat(70)}\n`);
    return context;
  }
}
