INPUT_COST_PER_1M  = 3.00   # dollars per 1M input tokens  (claude-sonnet-4-6)
OUTPUT_COST_PER_1M = 15.00  # dollars per 1M output tokens (claude-sonnet-4-6)


def calculate_cost(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens  / 1_000_000 * INPUT_COST_PER_1M +
            output_tokens / 1_000_000 * OUTPUT_COST_PER_1M)


def print_cost_summary(total_input: int, total_output: int) -> None:
    cost = calculate_cost(total_input, total_output)
    print(f"\n--- COST SUMMARY ---")
    print(f"Input tokens:  {total_input:,}")
    print(f"Output tokens: {total_output:,}")
    print(f"Cost this run: ${cost:.4f}")
    print(f"At 10,000 users: ${cost * 10_000:,.2f}")
