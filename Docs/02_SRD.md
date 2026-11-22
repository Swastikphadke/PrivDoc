# 02 --- Software Requirements Document (SRD)

## 1. Purpose

This SRD defines the externally observable requirements for PrivyDoc.
Requirement IDs should be referenced by implementation tasks and test
cases.

## 2. Scope

The baseline supports TXT and text-based PDF input, PII candidate
detection, user review, redacted export, safe summarization and local
feedback. Scanned PDFs and OCR are excluded.

## 3. Functional requirements

  -----------------------------------------------------------------------
  ID                      Requirement             Priority
  ----------------------- ----------------------- -----------------------
  FR-001                  The system shall accept Must
                          `.txt` files encoded as 
                          UTF-8, with a           
                          documented fallback for 
                          decoding errors.        

  FR-002                  The system shall accept Must
                          text-based `.pdf` files 
                          and extract page text   
                          and positional          
                          information.            

  FR-003                  The system shall detect Must
                          person names in running 
                          text, headers and       
                          signatures.             

  FR-004                  The system shall detect Must
                          likely initials and     
                          name variants and       
                          associate them with a   
                          common entity when      
                          evidence is sufficient. 

  FR-005                  The system shall detect Must
                          standard and supported  
                          lightly obfuscated      
                          email formats.          

  FR-006                  The system shall detect Must
                          mobile and landline     
                          phone numbers in        
                          supported formats,      
                          including configurable  
                          country rules.          

  FR-007                  The system shall detect Must
                          postal and street       
                          address candidates.     

  FR-008                  The system shall detect Must
                          configurable ID-like    
                          strings such as         
                          employee, student and   
                          account IDs.            

  FR-009                  Each candidate shall    Must
                          include a span, entity  
                          type, source detector,  
                          confidence or           
                          confidence band, and    
                          review status.          

  FR-010                  The system shall merge  Must
                          duplicate and           
                          overlapping detections  
                          without losing          
                          provenance.             

  FR-011                  The system shall        Must
                          display candidates      
                          highlighted in the      
                          document and            
                          distinguish             
                          types/confidence        
                          visually.               

  FR-012                  The user shall be able  Must
                          to approve or reject an 
                          individual candidate.   

  FR-013                  The user shall be able  Must
                          to manually select text 
                          and add a redaction     
                          with a chosen type.     

  FR-014                  The user shall be able  Must
                          to apply a decision to  
                          linked occurrences or a 
                          selected group of       
                          similar matches.        

  FR-015                  The system shall        Should
                          support keyboard        
                          shortcuts for common    
                          review actions.         

  FR-016                  The system shall not    Must
                          remove content before   
                          explicit user approval. 

  FR-017                  The system shall        Must
                          replace approved spans  
                          with configurable       
                          placeholders such as    
                          `[PERSON]` or           
                          `[EMAIL]`.              

  FR-018                  The system shall export Must
                          a redacted TXT copy.    

  FR-019                  The system shall export Must
                          a sanitized PDF copy    
                          with approved source    
                          text removed, not       
                          merely covered          
                          visually.               

  FR-020                  The system shall verify Must
                          exported files by       
                          reopening and checking  
                          for approved source     
                          values and relevant     
                          metadata/annotations.   

  FR-021                  The summarizer shall    Must
                          receive sanitized text  
                          only, never the         
                          original document text. 

  FR-022                  The system shall check  Must
                          summaries for exact     
                          approved values and     
                          known variants.         

  FR-023                  The system shall run a  Must
                          PII scan on generated   
                          summaries.              

  FR-024                  The system shall flag   Must
                          plausible               
                          quasi-identifier        
                          combinations and        
                          suppress or request     
                          review when risk is     
                          high.                   

  FR-025                  The system shall record Should
                          local user feedback on  
                          detections and          
                          corrections.            

  FR-026                  The system shall        Must
                          display clear errors    
                          for unsupported, empty, 
                          encrypted or image-only 
                          PDFs.                   

  FR-027                  The system shall allow  Must
                          the user to download    
                          the sanitized document  
                          and view/copy the safe  
                          summary.                

  FR-028                  The system shall clean  Must
                          up temporary files      
                          according to a          
                          documented retention    
                          policy.                 
  -----------------------------------------------------------------------

## 4. Non-functional requirements

  -----------------------------------------------------------------------
  ID                                  Requirement
  ----------------------------------- -----------------------------------
  NFR-001 Privacy                     Normal document processing and
                                      inference shall occur locally; no
                                      original content shall be sent to
                                      external APIs.

  NFR-002 Security                    Uploaded files shall be validated
                                      by extension, MIME/signature, size
                                      and parser outcome.

  NFR-003 Integrity                   Approved redactions shall be
                                      applied to the actual exported
                                      content.

  NFR-004 Usability                   A first-time user shall be able to
                                      complete the primary workflow with
                                      clear status and error messages.

  NFR-005 Performance                 The system shall report processing
                                      time and memory usage on the
                                      evaluation machine; targets are
                                      specified in the evaluation plan.

  NFR-006 Reliability                 A failed detection, export or
                                      summary step shall not be
                                      represented as successful.

  NFR-007 Maintainability             Detection methods shall be modular
                                      and independently testable.

  NFR-008 Portability                 The application shall run on a
                                      documented Windows/Linux
                                      development setup, subject to model
                                      runtime compatibility.

  NFR-009 Accessibility               Highlights shall use labels/icons
                                      as well as color; keyboard
                                      navigation shall be supported for
                                      review actions.

  NFR-010 Observability               Logs shall avoid storing raw
                                      document text or PII by default.

  NFR-011 Reproducibility             Model name/version, ruleset version
                                      and configuration shall be recorded
                                      for evaluation runs.

  NFR-012 Fail-safe behavior          If export verification or summary
                                      privacy checks fail, the unsafe
                                      output shall not be offered as
                                      safe.
  -----------------------------------------------------------------------

## 5. PII categories and handling

  ------------------------------------------------------------------------------
  Category                Examples                       Detection approach
  ----------------------- ------------------------------ -----------------------
  PERSON                  Full names, initials,          NER + SLM context +
                          title/name variants            entity linking

  EMAIL                   `person@example.com`,          Regex + normalization
                          supported obfuscations         

  PHONE                   Mobile, landline, country      Regex + number
                          code, separators               validation/context

  ADDRESS                 House/street/locality/postal   NER + contextual SLM
                          address                        

  ID_LIKE                 Employee, student, account,    Configurable patterns +
                          government ID-style strings    context
  ------------------------------------------------------------------------------

The system must not treat every date, number, product code or generic
organization name as PII. Context and user review are required.

## 6. User roles

Baseline has one local user role: document operator. No authentication
or multi-user permission system is required for the MVP.

## 7. Acceptance

A requirement is accepted only when its associated test passes and the
behavior is demonstrable. See the acceptance matrix in
`09_Deliverables_and_Acceptance.md`.
