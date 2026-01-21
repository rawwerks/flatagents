export type RunLengthConfig = {
  num_examples: number;
  correct_ratio: number;
  budget: number;
  pareto_set_size: number;
  minibatch_size: number;
  test_split: number;
  early_stop_patience: number;
};

export const RUN_LENGTH_DEFAULTS: RunLengthConfig = {
  num_examples: 6,
  correct_ratio: 0.3,
  budget: 1,
  pareto_set_size: 2,
  minibatch_size: 2,
  test_split: 0.2,
  early_stop_patience: 1,
};
