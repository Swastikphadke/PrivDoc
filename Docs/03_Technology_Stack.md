# 03 --- Technology Stack and Selection Rationale

## 1. Stack summary

  ------------------------------------------------------------------------
  Layer                   Baseline choice         Purpose
  ----------------------- ----------------------- ------------------------
  Frontend                React + Vite            Local web interface

  Language                JavaScript initially;   UI maintainability
                          TypeScript recommended  
                          if team is comfortable  

  Styling                 Tailwind CSS            Layout and styling

  Backend                 Python 3.11+ / FastAPI  API and orchestration

  Validation              Pydantic                Request/response schemas

  TXT                     Python standard library Text loading and offsets

  PDF                     PyMuPDF (`fitz`)        Text, word coordinates,
  extraction/redaction                            annotations and export

  Pattern detection       Python `re` + custom    Emails, phones and
                          validators              configurable IDs

  NER                     GLiNER as a candidate   Contextual entity spans
                          model; spaCy as an      
                          optional baseline       

  SLM                     Qwen2.5 Instruct        Contextual
                          family, quantized local disambiguation and
                          runtime                 structured suggestions

  Runtime                 Ollama for simplest     Local inference
                          local setup; llama.cpp  
                          as alternative          

  Fuzzy matching          RapidFuzz               Candidate alias
                                                  similarity

  Persistence             SQLite +                Local review and
                          SQLModel/SQLAlchemy     feedback metadata

  Testing                 pytest, httpx,          Backend and frontend
                          Vitest/React Testing    tests
                          Library                 

  Packaging               venv initially;         Development/deployment
                          optional Docker for     
                          reproducible packaging  
  ------------------------------------------------------------------------

## 2. Model strategy

Do not make the SLM the only detector. Use a hybrid architecture:

1.  Regex for structured patterns.
2.  NER for person/location/address candidates.
3.  SLM for ambiguous contextual classification and relationship
    suggestions.
4.  Entity resolution for linking occurrences.
5.  Human review for final authorization.

### Candidate models

-   Qwen2.5 0.5B/1.5B Instruct quantized: candidate for low-resource
    contextual tasks.
-   GLiNER: candidate for zero-shot or promptable span detection.
-   spaCy small English model: lightweight baseline and comparison.

Model availability, license, language coverage, RAM use and inference
speed must be checked before final selection. Pin exact model revisions
and record them in the project README.

## 3. Recommended initial configuration

Start with: - CPU inference. - One SLM loaded on demand. - Quantized
model where supported. - Small document chunks with overlap. - Regex and
NER running before SLM calls. - SLM only for uncertain candidates or
entity relationships.

Avoid loading multiple large models simultaneously on low-memory
devices. Benchmark the actual selected models on the target machine.

## 4. Why not use a cloud LLM?

The problem explicitly emphasizes privacy and local operation. Sending
original documents to a cloud model undermines that objective. Cloud
inference is therefore excluded from the baseline. Any future optional
remote mode would require explicit opt-in, a separate threat model and
clear disclosure.

## 5. Dependency management

-   Use a Python virtual environment.
-   Pin tested package versions in `requirements.txt` or a lock file.
-   Keep model weights outside source control.
-   Record model checksums/revisions where practical.
-   Store secrets/configuration in environment variables, never in Git.
-   Separate optional heavy dependencies from the minimal TXT/regex
    workflow.

## 6. Technology decision gates

Before locking the stack: 1. Test PDF extraction and redaction with
representative PDFs. 2. Compare GLiNER and spaCy on a small annotated
sample. 3. Benchmark the selected SLM on target hardware. 4. Validate
structured JSON output and timeout behavior. 5. Confirm licenses permit
the intended demonstration and distribution. 6. Confirm all normal
processing works offline after installation.
