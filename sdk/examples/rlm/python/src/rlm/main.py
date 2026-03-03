"""
RLM Example - Main Entry Point

Demonstrates the Recursive Language Model pattern for handling
arbitrarily long contexts through REPL exploration and recursive decomposition.

Based on arXiv:2512.24601 - "Recursive Language Models"

Usage:
    # Process a long document
    python -m rlm.main --file document.txt --task "What are the main themes?"

    # Process with custom chunk size
    python -m rlm.main --file data.json --task "Count all errors" --chunk-size 8000

    # Interactive mode
    python -m rlm.main --interactive
"""

import argparse
import asyncio
import sys
from pathlib import Path

from flatmachines import FlatMachine, HooksRegistry, setup_logging, get_logger
from rlm.hooks import RLMHooks

setup_logging(level='INFO')
logger = get_logger(__name__)


async def run_rlm(
    context: str,
    task: str,
    max_chunk_size: int = 16000,
    max_exploration_rounds: int = 5
) -> dict:
    """
    Run the RLM pipeline on a given context and task.

    Args:
        context: The full text context (can be arbitrarily long)
        task: The task/question to answer about the context
        max_chunk_size: Maximum size of chunks for recursive processing
        max_exploration_rounds: Maximum REPL exploration iterations

    Returns:
        Dictionary containing the answer and metadata
    """
    config_path = Path(__file__).parent.parent.parent.parent / 'config' / 'machine.yml'

    if not config_path.exists():
        raise FileNotFoundError(f"Machine config not found: {config_path}")

    registry = HooksRegistry()
    registry.register("rlm", RLMHooks)
    machine = FlatMachine(
        config_file=str(config_path),
        hooks_registry=registry,
    )

    logger.info(f"Starting RLM with context of {len(context)} characters")
    logger.info(f"Task: {task}")

    result = await machine.execute(input={
        "context": context,
        "task": task,
        "max_chunk_size": max_chunk_size,
        "max_exploration_rounds": max_exploration_rounds
    })

    logger.info(f"RLM completed. API calls: {machine.total_api_calls}, Cost: ${machine.total_cost:.4f}")

    return result


async def run_from_file(
    file_path: str,
    task: str,
    max_chunk_size: int = 16000,
    max_exploration_rounds: int = 5
) -> dict:
    """
    Run RLM on a file's contents.

    Args:
        file_path: Path to the file to process
        task: The task/question to answer
        max_chunk_size: Maximum chunk size
        max_exploration_rounds: Maximum exploration iterations

    Returns:
        Dictionary containing the answer and metadata
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    context = path.read_text(encoding='utf-8')
    logger.info(f"Loaded {len(context)} characters from {file_path}")

    return await run_rlm(
        context=context,
        task=task,
        max_chunk_size=max_chunk_size,
        max_exploration_rounds=max_exploration_rounds
    )


async def interactive_mode():
    """Run RLM in interactive mode."""
    print("=" * 60)
    print("RLM Interactive Mode")
    print("Based on arXiv:2512.24601 - Recursive Language Models")
    print("=" * 60)
    print()

    # Get context
    print("Enter the context (paste text, then press Ctrl+D or Ctrl+Z to finish):")
    print("-" * 40)

    try:
        context_lines = []
        while True:
            try:
                line = input()
                context_lines.append(line)
            except EOFError:
                break
        context = '\n'.join(context_lines)
    except KeyboardInterrupt:
        print("\nCancelled.")
        return

    if not context.strip():
        print("No context provided. Exiting.")
        return

    print(f"\nContext loaded: {len(context)} characters")
    print("-" * 40)

    # Get task
    print("\nEnter your task/question:")
    task = input("> ").strip()

    if not task:
        print("No task provided. Exiting.")
        return

    print("\nProcessing...")
    print("=" * 60)

    try:
        result = await run_rlm(context=context, task=task)

        print("\n" + "=" * 60)
        print("RESULT")
        print("=" * 60)
        print(f"\nAnswer: {result.get('answer', 'No answer')}")
        print(f"\nConfidence: {result.get('confidence', 'unknown')}")
        print(f"\nMethod: {result.get('method', 'unknown')}")

        if result.get('reasoning'):
            print(f"\nReasoning: {result.get('reasoning')}")

        if result.get('caveats'):
            print(f"\nCaveats: {', '.join(result.get('caveats', []))}")

        print(f"\nExploration rounds: {result.get('exploration_rounds', 0)}")
        print(f"Sub-tasks processed: {result.get('sub_tasks_processed', 0)}")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise


def demo():
    """Run a demo with sample content."""
    # Generate a sample document with fewer sections to minimize LLM calls
    sample_sections = []
    for i in range(5):
        sample_sections.append(f"""
## Section {i + 1}: Topic Alpha-{i}

This is the content of section {i + 1}. It contains various information
about topic Alpha-{i}. The key finding in this section is that the value
for metric X is {i * 17 % 100}.

Additional details include:
- Point A: {i * 3}
- Point B: {i * 7}
- Point C: {i * 11}

{"IMPORTANT: The secret code is RLM-" + str(42 + i) if i == 2 else ""}
""")

    context = "\n".join(sample_sections)

    task = "What is the secret code mentioned in the document?"

    print("=" * 60)
    print("RLM Demo")
    print("=" * 60)
    print(f"Context: {len(context)} characters (~{len(context)//4} tokens)")
    print(f"Task: {task}")
    print("=" * 60)

    result = asyncio.run(run_rlm(context=context, task=task))

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"Answer: {result.get('answer', 'No answer')}")
    print(f"Method: {result.get('method', 'unknown')}")
    print(f"Exploration rounds: {result.get('exploration_rounds', 0)}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Recursive Language Model - Process arbitrarily long contexts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process a file
    python -m rlm.main --file document.txt --task "Summarize the main points"

    # Interactive mode
    python -m rlm.main --interactive

    # Run demo
    python -m rlm.main --demo
"""
    )

    parser.add_argument(
        '--file', '-f',
        help='Path to file containing the context'
    )
    parser.add_argument(
        '--task', '-t',
        help='Task or question to answer about the context'
    )
    parser.add_argument(
        '--chunk-size', '-c',
        type=int,
        default=16000,
        help='Maximum chunk size for processing (default: 16000)'
    )
    parser.add_argument(
        '--max-rounds', '-r',
        type=int,
        default=5,
        help='Maximum exploration rounds (default: 5)'
    )
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Run in interactive mode'
    )
    parser.add_argument(
        '--demo', '-d',
        action='store_true',
        help='Run demo with sample content'
    )

    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.interactive:
        asyncio.run(interactive_mode())
    elif args.file and args.task:
        result = asyncio.run(run_from_file(
            file_path=args.file,
            task=args.task,
            max_chunk_size=args.chunk_size,
            max_exploration_rounds=args.max_rounds
        ))
        print(f"\nAnswer: {result.get('answer', 'No answer')}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
