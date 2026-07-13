from intake_service import run_intake_service
from search_format_service import run_search_format_service
from renderers import render_terminal, render_pdf
from track_cost import print_cost_summary


def main() -> None:
    preferences, intake_usage = run_intake_service()

    itinerary, search_usage = run_search_format_service(preferences)

    render_terminal(itinerary)
    render_pdf(itinerary)

    total_input  = intake_usage[0]  + search_usage[0]
    total_output = intake_usage[1]  + search_usage[1]
    print_cost_summary(total_input, total_output)


if __name__ == "__main__":
    main()
