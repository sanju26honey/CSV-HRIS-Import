from django.shortcuts import render
from preview.services import analyze_csv, ImportFormatError


def index(request):
    """
    Renders the HRIS import page. Handles CSV file upload and passes
    analyzed data or format errors to the view template.
    """
    context = {
        "result": None,
        "format_error": None,
    }

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            context["format_error"] = "Please select a CSV file."
        else:
            try:
                result = analyze_csv(uploaded_file)
                context["result"] = result
            except ImportFormatError as exc:
                context["format_error"] = str(exc)
            except Exception as exc:
                context["format_error"] = f"An error occurred while processing the CSV file: {exc}"

    return render(request, "preview/index.html", context)
