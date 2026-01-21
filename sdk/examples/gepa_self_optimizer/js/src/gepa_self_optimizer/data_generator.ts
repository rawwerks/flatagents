import { join } from 'path';
import { loadAgent, saveJson, createLogger } from './utils.js';
import { RUN_LENGTH_DEFAULTS } from './run_length.js';

export class DataGenerator {
  static ERROR_TYPES: Record<string, string> = {
    NONE: 'PASS',
    FACTUAL_ERROR: 'FAIL_MAJOR',
    LOGICAL_FLAW: 'FAIL_MAJOR',
    INCOMPLETE: 'FAIL_MINOR',
    SUBTLE_MISTAKE: 'FAIL_MINOR',
    HALLUCINATION: 'FAIL_CRITICAL',
    MISUNDERSTANDING: 'FAIL_MAJOR',
  };

  static DOMAINS = ['coding', 'reasoning', 'factual', 'math'];
  static DIFFICULTIES = ['easy', 'medium', 'hard'];

  private taskGenerator;
  private responseGenerator;
  private logger;
  private stats = {
    task_generator_calls: 0,
    response_generator_calls: 0,
    task_generator_cost: 0,
    response_generator_cost: 0,
  };

  constructor(private configDir: string, options: { verbose?: boolean } = {}) {
    const agentsDir = join(configDir, 'agents');
    this.taskGenerator = loadAgent(join(agentsDir, 'task_generator.yml'));
    this.responseGenerator = loadAgent(join(agentsDir, 'response_generator.yml'));
    this.logger = createLogger(options.verbose ?? true);
    this.logger.info('DataGenerator initialized with flatagents');
  }

  async generateTask(domain: string, difficulty: string): Promise<Record<string, any>> {
    this.stats.task_generator_calls += 1;
    return this.taskGenerator.call({ domain, difficulty });
  }

  async generateResponse(task: string, correctResponse: string, errorType: string): Promise<Record<string, any>> {
    this.stats.response_generator_calls += 1;
    return this.responseGenerator.call({ task, correct_response: correctResponse, error_type: errorType });
  }

  async generateExample(options: { domain?: string; difficulty?: string; errorType?: string } = {}): Promise<Record<string, any>> {
    const domain = options.domain ?? DataGenerator.DOMAINS[Math.floor(Math.random() * DataGenerator.DOMAINS.length)];
    const difficulty = options.difficulty ?? DataGenerator.DIFFICULTIES[Math.floor(Math.random() * DataGenerator.DIFFICULTIES.length)];
    const errorType = options.errorType ?? Object.keys(DataGenerator.ERROR_TYPES)[Math.floor(Math.random() * Object.keys(DataGenerator.ERROR_TYPES).length)];

    this.logger.info(`Generating example: domain=${domain}, difficulty=${difficulty}, error=${errorType}`);

    const taskResult = await this.generateTask(domain, difficulty);
    const taskOutput = taskResult.output ?? {};

    const responseResult = await this.generateResponse(
      taskOutput.task ?? '',
      taskOutput.correct_response ?? '',
      errorType,
    );
    const responseOutput = responseResult.output ?? {};

    return {
      task: taskOutput.task ?? '',
      correct_response: taskOutput.correct_response ?? '',
      evaluation_criteria: taskOutput.evaluation_criteria ?? '',
      key_elements: taskOutput.key_elements ?? [],
      agent_response: responseOutput.response ?? '',
      has_error: responseOutput.has_error ?? false,
      error_type: errorType,
      error_description: responseOutput.error_description ?? '',
      expected_verdict: responseOutput.expected_verdict ?? DataGenerator.ERROR_TYPES[errorType] ?? 'PASS',
      domain,
      difficulty,
    };
  }

  async generateDataset(
    numExamples = RUN_LENGTH_DEFAULTS.num_examples,
    correctRatio = RUN_LENGTH_DEFAULTS.correct_ratio,
  ): Promise<Array<Record<string, any>>> {
    const examples: Array<Record<string, any>> = [];
    const numCorrect = Math.floor(numExamples * correctRatio);
    const numErrors = numExamples - numCorrect;

    this.logger.info(`Generating dataset with ${numExamples} examples`);

    for (let i = 0; i < numCorrect; i += 1) {
      this.logger.info(`Generating correct example ${i + 1}/${numCorrect}`);
      const example = await this.generateExample({ errorType: 'NONE' });
      examples.push(example);
    }

    const errorTypes = Object.keys(DataGenerator.ERROR_TYPES).filter(type => type !== 'NONE');
    for (let i = 0; i < numErrors; i += 1) {
      const errorType = errorTypes[i % errorTypes.length];
      this.logger.info(`Generating error example ${i + 1}/${numErrors} (${errorType})`);
      const example = await this.generateExample({ errorType });
      examples.push(example);
    }

    this.logger.info(`Generated ${examples.length} examples`);

    return examples.sort(() => Math.random() - 0.5);
  }

  saveDataset(examples: Array<Record<string, any>>, outputPath: string): void {
    saveJson(examples, outputPath);
    this.logger.info(`Saved dataset to ${outputPath}`);
  }

  getStats(): Record<string, number> {
    return { ...this.stats };
  }
}
