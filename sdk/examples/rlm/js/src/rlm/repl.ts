import vm from 'vm';

export type ReplResult = {
  success: boolean;
  output: string;
  error: string;
  return_value: any;
};

export class REPLExecutor {
  private timeout: number;
  private globalState: Record<string, any> = {};
  private executionHistory: Array<{ code: string; result: ReplResult }> = [];
  private context: vm.Context;

  constructor(timeout = 30) {
    this.timeout = timeout;
    this.setupBuiltins();
    this.context = vm.createContext(this.globalState);
  }

  private setupBuiltins(): void {
    this.globalState = {
      ...this.globalState,
      JSON,
      Math,
      Number,
      String,
      Boolean,
      Array,
      Object,
      RegExp,
      Map,
      Set,
      Date,
      parseInt,
      parseFloat,
      isNaN,
    };
  }

  setContext(content: string, variableName = 'INPUT'): void {
    this.globalState[variableName] = content;
    this.globalState._context_length = content.length;
    this.globalState._context_tokens = Math.floor(content.length / 4);
  }

  execute(code: string): ReplResult {
    const outputBuffer: string[] = [];
    const result: ReplResult = {
      success: false,
      output: '',
      error: '',
      return_value: null,
    };

    this.globalState.print = (...args: any[]) => {
      outputBuffer.push(args.map(arg => String(arg)).join(' '));
    };
    this.globalState.console = {
      log: (...args: any[]) => outputBuffer.push(args.map(arg => String(arg)).join(' ')),
      error: (...args: any[]) => outputBuffer.push(args.map(arg => String(arg)).join(' ')),
    };

    try {
      vm.runInContext(code, this.context, { timeout: this.timeout * 1000 });

      const lines = code.trim().split('\n');
      const lastLine = lines[lines.length - 1]?.trim();
      if (lastLine && !/^(if|for|while|function|class|try|catch|const|let|var|import|export|return|throw|break|continue|\/)/.test(lastLine)) {
        try {
          result.return_value = vm.runInContext(lastLine, this.context, { timeout: this.timeout * 1000 });
        } catch {
          // Ignore evaluation errors for last line
        }
      }

      result.success = true;
      result.output = outputBuffer.join('\n');
    } catch (error) {
      result.error = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
      result.output = outputBuffer.join('\n');
    }

    this.executionHistory.push({ code, result });
    return result;
  }

  getHistory(): Array<{ code: string; result: ReplResult }> {
    return this.executionHistory;
  }

  reset(): void {
    const contextContent = this.globalState.INPUT;
    this.globalState = {};
    this.setupBuiltins();
    if (contextContent) {
      this.setContext(contextContent);
    }
    this.context = vm.createContext(this.globalState);
    this.executionHistory = [];
  }

  getStatistics(): Record<string, number> {
    const successful = this.executionHistory.filter(entry => entry.result.success).length;
    return {
      total_executions: this.executionHistory.length,
      successful_executions: successful,
      failed_executions: this.executionHistory.length - successful,
      context_length: this.globalState._context_length ?? 0,
      estimated_tokens: this.globalState._context_tokens ?? 0,
    };
  }
}
