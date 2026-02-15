# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install system dependencies
# tesseract-ocr: for academic plan/faculty photo OCR
# libgl1-mesa-glx: required by some image processing libs
# poppler-utils: for pdfplumber's image conversion
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    poppler-utils \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app runs on
EXPOSE 8000

# Set environment variables
ENV HOST=0.0.0.0
ENV PORT=8000

# Run the application
CMD ["python", "main.py"]
