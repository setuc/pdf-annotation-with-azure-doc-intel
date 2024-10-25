# Azure Document Intelligence PDF Markup Script

## Overview

This script allows you to annotate PDF documents based on analysis results from **Azure Document Intelligence**. It processes key-value pairs, tables, and paragraphs from a JSON analysis result file and overlays visual annotations onto the corresponding regions in the PDF. Additionally, the script visually represents confidence scores for each key-value pair by drawing a color-coded bar next to the annotations, providing a quick visual indication of the recognition confidence.

## Features

- **Command-Line Interface**: Easily process PDFs directly from the command line.
- **Visual Annotations**: Annotate key-value pairs, tables, and paragraphs directly on the PDF.
- **Confidence Indicators**: Draws color-coded confidence bars next to key-value annotations to represent confidence scores.
- **Logging**: Provides detailed, color-coded logging output for tracking processing progress and debugging.

## Requirements

- **Python 3.10 or higher**

  > **Note:** The script is compatible with Python 3.8 and above. Ensure you have an appropriate Python version installed.

- **Python Packages**: All required packages are listed in `requirements.txt`.

## Installation

1. **Clone or Download the Repository**

   Clone the repository or copy the `python` folder containing the script and its dependencies.

2. **Navigate to the `python` Folder**

   ```bash
   cd python
   ```

3. **(Optional) Create a Virtual Environment**

   It's recommended to use a virtual environment to manage dependencies.

   ```bash
   python -m venv .venv
   ```

   Activate the virtual environment:

   - **On Windows:**

     ```bash
     .\.venv\Scripts\activate
     ```

   - **On macOS/Linux:**

     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies**

   Install the required Python packages using `pip`:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

You can run the `markup_pdf.py` script by providing the paths to the input PDF file, the JSON file containing the analysis results from Azure Document Intelligence, and the desired output PDF file path.

```bash
python markup_pdf.py INPUT_PDF_PATH INPUT_JSON_PATH OUTPUT_PDF_PATH
```

- `INPUT_PDF_PATH`: Path to the input PDF document you want to annotate.
- `INPUT_JSON_PATH`: Path to the JSON file containing the analysis results from Azure Document Intelligence.
- `OUTPUT_PDF_PATH`: Path where the annotated PDF will be saved.

### Example

Suppose you have a PDF file `Citizens_Direct_Deposit_Form.pdf` and its corresponding analysis results in `Citizens_Direct_Deposit_Form.pdf.json`. To annotate the PDF and save the result as `Marked_Citizens_Direct_Deposit_Form.pdf`, run:

```bash
python markup_pdf.py ../examples/Citizens_Direct_Deposit_Form.pdf ../examples/Citizens_Direct_Deposit_Form.pdf.json ../examples/Marked_Citizens_Direct_Deposit_Form.pdf
```

**Note:** Ensure that the input files exist at the specified paths and that you have write permissions for the output path.

## Features in Detail

### Visual Annotations

The script processes the following elements from the JSON analysis results and overlays annotations on the PDF:

- **Key-Value Pairs**: Draws rectangles around keys and values with varying opacity and colors to differentiate between different pairs.
- **Tables**: Highlights table cells, differentiating headers from data cells using different styles.
- **Paragraphs**: Marks paragraphs with a light background for visual distinction.

### Confidence Indicators

For each key-value pair, the script draws a color-coded bar next to the annotation to indicate the confidence score:

- **Low Confidence (Red)**: Confidence scores closer to 0.
- **High Confidence (Green)**: Confidence scores closer to 1.
- **Gradient Transition**: Smooth color transition from red through yellow to green as confidence increases.

This visual representation provides quick feedback on the accuracy of the recognition.

### Logging

The script uses the `coloredlogs` package to provide colored logging output, making it easier to track progress and identify any warnings or errors during processing.

- **Info Messages**: Indicate normal operation and progress.
- **Warnings**: Highlight potential issues, such as missing key-value pairs in the JSON data.
- **Errors**: Report critical failures or exceptions that prevent processing.

## Dependencies

The script relies on the following Python packages:

- **[PyMuPDF (fitz)](https://pymupdf.readthedocs.io/en/latest/)**: For PDF processing and manipulation.
- **[coloredlogs](https://coloredlogs.readthedocs.io/en/latest/)**: For color-coded logging output in the console.

All dependencies are specified in `requirements.txt` and can be installed using:

```bash
pip install -r requirements.txt
```

## Notes and Tips

- **Coordinate Scaling**: The script scales the polygon coordinates from the JSON file by multiplying by 72 to convert them to PDF points (as PDF coordinates are in points). Adjust the scaling factor if your data uses different units.

- **JSON Structure**: Ensure that the JSON file follows the structure provided by Azure Document Intelligence when analyzing documents using the **General Document Layout** and **Key Value Pairs** features.

- **Input Validation**: The script assumes that the input PDF and JSON files are valid and correspond to each other.

- **Console Compatibility**: If your console does not support colored output, the log messages may appear without colors or with special characters.

## Troubleshooting

- **No Key-Value Pairs Found**: If a warning about missing key-value pairs appears, verify that the JSON file contains the `keyValuePairs` field with appropriate data.

- **Missing Modules Error**: If you encounter errors like `ModuleNotFoundError`, ensure that all dependencies are installed correctly in your environment.

- **Permission Denied**: If the script cannot read input files or write the output file, check your file paths and ensure you have the necessary permissions.

- **Invalid JSON Format**: If there's an error parsing the JSON file, ensure it is correctly formatted and corresponds to the expected structure.

## Helpful Resources

- **Azure Document Intelligence (Form Recognizer)**:
  - [Azure Form Recognizer Documentation](https://docs.microsoft.com/azure/applied-ai-services/form-recognizer/)
  - [Quickstart: Extract information from forms](https://docs.microsoft.com/azure/applied-ai-services/form-recognizer/quickstarts/try-v3-form-layout-api)

- **PyMuPDF Documentation**:
  - [PyMuPDF (Python bindings for MuPDF)](https://pymupdf.readthedocs.io/en/latest/)

- **Python Logging**:
  - [Coloredlogs Documentation](https://coloredlogs.readthedocs.io/en/latest/)

## Support

If you have any issues or questions, please open an issue on the repository or contact the maintainer.

---

By following these instructions, you should be able to use the `markup_pdf.py` script to annotate PDF documents based on analysis results from Azure Document Intelligence. This enhances your document processing workflows by providing visual representations of extracted data and their confidence levels.

**Feel free to reach out if you have any questions or need further assistance!**

---

# Files Included in the `python` Folder

- `markup_pdf.py`: The Python script for annotating PDFs directly from the command line.
- `requirements.txt`: Lists the Python dependencies required to run `markup_pdf.py`.
- `README.md`: This documentation file providing details on installation and usage of the script.

---

# Folder Structure

Your `python` folder should now contain the following files:

- `markup_pdf.py`
- `requirements.txt`
- `README.md`

---

# Additional Notes

- **Color-Coded Logging**: The script uses the `coloredlogs` package to provide color-coded logging output in the console. This improves readability by differentiating information, warnings, and errors with different colors.

- **Running Without the Web App**: This script allows users to process PDFs locally without running the full web application or Azure Functions backend.

- **Data Files**: Ensure that you have the necessary PDF and JSON data files in the correct paths when running the script. The examples assume you have the data files in an `examples` directory.

---

# Integration with the Overall Package

This script is part of the **Azure Document Intelligence Result Processor** project, which provides tools for processing PDF documents using Azure's AI services. While the web application offers a user-friendly interface for processing and viewing annotated PDFs, the `markup_pdf.py` script provides a command-line alternative for batch processing or integration into other workflows.

---

**Remember to consult the main project's `README.md` for additional context and instructions if you're integrating this script into the larger application stack.**

---

# Contributing

Contributions are welcome! If you'd like to contribute to this project, please follow these steps:

1. **Fork the Repository**

2. **Create a Feature Branch**

   ```bash
   git checkout -b feature/YourFeatureName
   ```

3. **Commit Your Changes**

   ```bash
   git commit -am 'Add some feature'
   ```

4. **Push to the Branch**

   ```bash
   git push origin feature/YourFeatureName
   ```

5. **Open a Pull Request**

---

# Contact Information

For any questions or assistance, please reach out:

- **GitHub Issues**: [Repository's issues page](https://github.com/setuc/pdf-annotation-with-azure-doc-intel/issues)

