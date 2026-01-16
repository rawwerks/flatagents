import * as nunjucks from "nunjucks";
import * as yaml from "yaml";
import { readFileSync } from 'fs';
import { AgentConfig } from './types';
import { MCPToolProvider } from './mcp';
import { LLMBackend, Message, VercelAIBackend } from './llm';

/**
 * Options for constructing a FlatAgent with custom backends.
 */
export interface AgentOptions {
  /** Path to YAML config file or inline AgentConfig */
  config: string | AgentConfig;

  /** Custom LLM backend (if not provided, uses VercelAIBackend based on config) */
  llmBackend?: LLMBackend;

  /** Base directory for resolving relative paths */
  configDir?: string;
}

export class FlatAgent {
  public config: AgentConfig;
  private mcpProvider?: MCPToolProvider;
  private llmBackend?: LLMBackend;

  /**
   * Create a FlatAgent.
   *
   * @param configOrOptions - Config path, config object, or AgentOptions
   */
  constructor(configOrOptions: AgentConfig | string | AgentOptions) {
    if (configOrOptions && typeof configOrOptions === 'object' && 'config' in configOrOptions && !('spec' in configOrOptions)) {
      // AgentOptions provided
      const options = configOrOptions as AgentOptions;
      this.config = typeof options.config === 'string'
        ? yaml.parse(readFileSync(options.config, 'utf-8')) as AgentConfig
        : options.config;
      this.llmBackend = options.llmBackend;
    } else if (typeof configOrOptions === 'string') {
      // Path provided
      this.config = yaml.parse(readFileSync(configOrOptions, 'utf-8')) as AgentConfig;
    } else {
      // AgentConfig provided directly
      this.config = configOrOptions as AgentConfig;
    }

    const configData = this.config && typeof this.config === "object"
      ? (this.config as any).data
      : undefined;
    if (configData?.expression_engine === "cel") {
      throw new Error("expression_engine 'cel' is not supported in the JS SDK yet");
    }
  }

  /**
   * Get or create the LLM backend.
   */
  private getBackend(): LLMBackend {
    if (!this.llmBackend) {
      this.llmBackend = new VercelAIBackend({
        provider: this.config.data.model.provider ?? 'openai',
        name: this.config.data.model.name,
      });
    }
    return this.llmBackend;
  }

  async call(input: Record<string, any>): Promise<{ content: string; output: any }> {
    // Connect MCP if configured
    if (this.config.data.mcp && !this.mcpProvider) {
      this.mcpProvider = new MCPToolProvider();
      await this.mcpProvider.connect(this.config.data.mcp.servers);
    }

    // Render prompts
    const tools = this.mcpProvider ? await this.mcpProvider.listTools(this.config.data.mcp?.tool_filter) : [];
    const toolsPrompt = this.config.data.mcp?.tool_prompt
      ? nunjucks.renderString(this.config.data.mcp.tool_prompt, { tools })
      : "";
    const templateVars = { input, tools, tools_prompt: toolsPrompt, model: this.config.data.model };
    const system = nunjucks.renderString(this.config.data.system, templateVars);
    let user = nunjucks.renderString(this.config.data.user, templateVars);
    if (this.config.data.instruction_suffix) {
      user = `${user}\n\n${this.config.data.instruction_suffix}`;
    }

    // Build messages for LLM backend
    const messages: Message[] = [
      { role: 'system', content: system },
      { role: 'user', content: user },
    ];

    // Get model config options
    const modelConfig = this.config.data.model;

    // Call LLM via backend
    const backend = this.getBackend();
    const text = await backend.call(messages, {
      temperature: modelConfig.temperature,
      max_tokens: modelConfig.max_tokens,
      top_p: modelConfig.top_p,
      frequency_penalty: modelConfig.frequency_penalty,
      presence_penalty: modelConfig.presence_penalty,
    });

    // Extract structured output
    const output = this.extractOutput(text);
    return { content: text, output };
  }

  private extractOutput(text: string): any {
    // Strip markdown fences and parse JSON
    const match = text.match(/```(?:json)?\s*([\s\S]*?)```/);
    const json = match ? match[1].trim() : text.trim();

    try {
      const parsed = JSON.parse(json);

      // If we got a primitive but have a schema expecting an object,
      // map it to the first field
      if (this.config.data.output && parsed !== null && typeof parsed !== 'object') {
        const fields = Object.keys(this.config.data.output);
        if (fields.length === 1) {
          return { [fields[0]]: parsed };
        }
      }

      return parsed;
    } catch {
      // If JSON parsing fails, check if we have a single field schema
      // and the response looks like a quoted value
      if (this.config.data.output) {
        const fields = Object.keys(this.config.data.output);
        if (fields.length === 1) {
          // Try strict match first - entire response is quoted
          const strictMatch = json.trim().match(/^"([^"]*)"$/);
          if (strictMatch) {
            return { [fields[0]]: strictMatch[1] };
          }
          // Fall back to finding any quoted string in response
          const lenientMatch = json.match(/"([^"]+)"/);
          if (lenientMatch) {
            return { [fields[0]]: lenientMatch[1] };
          }
          // If not quoted, use the raw text as the value
          if (json.trim()) {
            return { [fields[0]]: json.trim() };
          }
        }
      }
      return { content: text };
    }
  }
}
