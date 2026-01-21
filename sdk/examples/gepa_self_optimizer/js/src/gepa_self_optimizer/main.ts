#!/usr/bin/env node
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import { existsSync } from 'fs';
import { DataGenerator } from './data_generator.js';
import { JudgeEvaluator } from './evaluator.js';
import { GEPASelfOptimizer } from './optimizer.js';
import { loadJson } from './utils.js';
import { RUN_LENGTH_DEFAULTS } from './run_length.js';

function parseArgs(argv: string[]) {
  const args: Record<string, any> = { command: argv[0] };
  for (let i = 1; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg.startsWith('--')) {
      const key = arg.replace(/^--/, '');
      const next = argv[i + 1];
      if (next && !next.startsWith('--')) {
        args[key] = next;
        i += 1;
      } else {
        args[key] = true;
      }
    }
  }
  return args;
}

async function cmdRun(args: Record<string, any>, configDir: string, outputDir: string) {
  const verbose = !args.quiet;
  const optimizer = new GEPASelfOptimizer(configDir, outputDir, {
    budget: Number(args.budget ?? RUN_LENGTH_DEFAULTS.budget),
    pareto_set_size: Number(args['pareto-size'] ?? RUN_LENGTH_DEFAULTS.pareto_set_size),
    minibatch_size: Number(args['minibatch-size'] ?? RUN_LENGTH_DEFAULTS.minibatch_size),
    verbose,
  });

  const result = await optimizer.optimize(
    Number(args['num-examples'] ?? RUN_LENGTH_DEFAULTS.num_examples),
    Boolean(args['force-regenerate']),
  );

  console.log('='.repeat(60));
  console.log('GEPA OPTIMIZATION COMPLETE');
  console.log('='.repeat(60));
  console.log(`Initial accuracy:   ${result.initial_accuracy.toFixed(1)}%`);
  console.log(`Final accuracy:     ${result.final_accuracy.toFixed(1)}%`);
  console.log(`Improvement:        ${result.total_improvement >= 0 ? '+' : ''}${result.total_improvement.toFixed(1)}%`);
  console.log(`Iterations:         ${result.iterations.length}`);
  console.log(`Population size:    ${result.population_size}`);
  console.log(`Best candidate:     ${result.best_candidate_id}`);
  console.log(`Best lineage:       ${JSON.stringify(result.best_lineage)}`);
  console.log(`Total LLM calls:    ${result.total_llm_calls}`);
  console.log(`Estimated cost:     $${result.total_cost.toFixed(4)}`);
  console.log(`Optimized judge saved to: ${join(outputDir, 'optimized_judge.yml')}`);
}

async function cmdGenerateData(args: Record<string, any>, configDir: string, dataDir: string) {
  const generator = new DataGenerator(configDir, { verbose: !args.quiet });
  const numExamples = Number(args['num-examples'] ?? RUN_LENGTH_DEFAULTS.num_examples);
  const correctRatio = Number(args['correct-ratio'] ?? RUN_LENGTH_DEFAULTS.correct_ratio);
  const outputPath = args.output ?? join(dataDir, 'evaluation_set.json');

  const examples = await generator.generateDataset(numExamples, correctRatio);
  generator.saveDataset(examples, outputPath);

  const stats = generator.getStats();

  console.log('='.repeat(60));
  console.log('DATA GENERATION COMPLETE');
  console.log('='.repeat(60));
  console.log(`Examples generated: ${examples.length}`);
  console.log(`Output path: ${outputPath}`);
  console.log(`Task generator calls: ${stats.task_generator_calls}`);
  console.log(`Response generator calls: ${stats.response_generator_calls}`);

  const verdicts: Record<string, number> = {};
  const domains: Record<string, number> = {};
  examples.forEach(example => {
    const verdict = example.expected_verdict ?? 'PASS';
    const domain = example.domain ?? 'unknown';
    verdicts[verdict] = (verdicts[verdict] ?? 0) + 1;
    domains[domain] = (domains[domain] ?? 0) + 1;
  });

  console.log(`Verdict distribution: ${JSON.stringify(verdicts)}`);
  console.log(`Domain distribution: ${JSON.stringify(domains)}`);
}

async function cmdEvaluate(args: Record<string, any>, configDir: string, dataDir: string) {
  const judgePath = args.judge ?? join(configDir, 'agents', 'judge.yml');
  const dataPath = args.data ?? join(dataDir, 'evaluation_set.json');
  const verbose = !args.quiet;

  if (!existsSync(dataPath)) {
    console.error(`Data file not found: ${dataPath}`);
    console.info("Run 'generate-data' first.");
    return;
  }

  const evaluator = new JudgeEvaluator({ judgeConfigPath: judgePath, verbose });
  const examples = loadJson<Array<Record<string, any>>>(dataPath);
  const result = await evaluator.evaluateDataset(examples, verbose);

  console.log('='.repeat(60));
  console.log('EVALUATION RESULTS');
  console.log('='.repeat(60));
  console.log(`Judge: ${judgePath}`);
  console.log(`Examples: ${examples.length}`);
  console.log(`Accuracy:           ${result.accuracy.toFixed(1)}%`);
  console.log(`Balanced Accuracy:  ${result.balancedAccuracy.toFixed(1)}%`);
  console.log(`False Positive Rate: ${result.falsePositiveRate.toFixed(1)}%`);
  console.log(`False Negative Rate: ${result.falseNegativeRate.toFixed(1)}%`);
  console.log(`Calibration Error:  ${result.calibrationError.toFixed(3)}`);
  console.log(`Failures: ${result.failures.length}`);
  console.log(`API calls: ${result.totalCalls}`);
  console.log(`Estimated cost: $${result.totalCost.toFixed(4)}`);

  if (result.failures.length) {
    console.log('Sample failures:');
    result.failures.slice(0, 3).forEach(failure => {
      console.log(`  - Expected: ${failure.expected_verdict}, Got: ${failure.predicted_verdict}`);
    });
  }
}

async function cmdOptimize(args: Record<string, any>, configDir: string, outputDir: string) {
  const verbose = !args.quiet;
  const optimizer = new GEPASelfOptimizer(configDir, outputDir, {
    budget: Number(args.budget ?? RUN_LENGTH_DEFAULTS.budget),
    pareto_set_size: Number(args['pareto-size'] ?? RUN_LENGTH_DEFAULTS.pareto_set_size),
    minibatch_size: Number(args['minibatch-size'] ?? RUN_LENGTH_DEFAULTS.minibatch_size),
    verbose,
  });

  const result = await optimizer.optimize(Number(args['num-examples'] ?? RUN_LENGTH_DEFAULTS.num_examples), false);
  console.log('Optimization complete.');
  console.log(`Final accuracy: ${result.final_accuracy.toFixed(1)}%`);
  console.log(`Optimized judge saved to: ${join(outputDir, 'optimized_judge.yml')}`);
}

async function main() {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  const exampleRoot = join(__dirname, '..', '..', '..');
  const configDir = join(exampleRoot, 'config');
  const outputDir = join(exampleRoot, 'output');
  const dataDir = join(exampleRoot, 'data');

  const args = parseArgs(process.argv.slice(2));
  const command = args.command ?? 'run';

  if (command === 'run') {
    await cmdRun(args, configDir, outputDir);
    return;
  }

  if (command === 'generate-data') {
    await cmdGenerateData(args, configDir, dataDir);
    return;
  }

  if (command === 'evaluate') {
    await cmdEvaluate(args, configDir, dataDir);
    return;
  }

  if (command === 'optimize') {
    await cmdOptimize(args, configDir, outputDir);
    return;
  }

  console.error('Unknown command. Use: run | generate-data | evaluate | optimize');
  process.exit(1);
}

main().catch(error => {
  console.error('Error:', error);
  process.exit(1);
});
