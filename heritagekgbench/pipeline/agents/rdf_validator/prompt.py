RDF_VALIDATION_PROMPT = """
<task_definition>
Your task is to validate and repair RDF data to ensure it is syntactically correct Turtle format.
1.  Analyze the input text to identify RDF triples.
2.  Check for missing prefixes. If a prefix (e.g., `ns1:`, `wd:`) is used in a triple but not defined at the top, YOU MUST generate a definition for it.
3.  Fix syntactic errors such as missing periods, malformed URIs, or incorrect semicolon usage.
4.  Return the fully corrected, valid RDF graph.
5.  **After generating your corrected Turtle output, you MUST call the `validate_turtle_syntax` tool** with the full Turtle string (including prefix declarations) to verify it parses correctly. If the tool returns `valid: false`, read the error message, fix the issue, and call the tool again. Repeat until it returns `valid: true`.
</task_definition>

<output_specification>
-   The output must be a valid RDF graph in **Turtle (.ttl)** syntax.
-   The output must be enclosed in markdown code blocks: ```turtle ... ```.
-   **CRITICAL:** All prefixes used in the body (e.g., `ns1:`, `rdfs:`) must have a corresponding `@prefix` declaration at the top of the file.
-   **CRITICAL:** Each prefix MUST be declared exactly once. Do NOT produce duplicate `@prefix` lines. If the same prefix appears more than once, keep only the first declaration and remove the rest.
-   If the input is empty or clearly not RDF data, return the exact string: "No input provided."
-   DO NOT output any text, explanation, or commentary outside the code block.
</output_specification>



<examples>
    <example>
        <input_text>
ex:John a ns1:Person ;
    ns1:knows ex:Mary
        </input_text>
        <output_turtle>
```turtle
@prefix ex: [http://example.org/](http://example.org/) .
@prefix ns1: [http://example.org/ns1/](http://example.org/ns1/) .

ex:John a ns1:Person ;
    ns1:knows ex:Mary .
    </output_turtle>
</example>

<example>
    <input_text>
@prefix foaf: http://xmlns.com/foaf/0.1/ . foaf:Person rdfs:label "Person" . </input_text> <output_turtle>

Codefragment

@prefix foaf: [http://xmlns.com/foaf/0.1/](http://xmlns.com/foaf/0.1/) .
@prefix rdfs: [http://www.w3.org/2000/01/rdf-schema#](http://www.w3.org/2000/01/rdf-schema#) .

foaf:Person rdfs:label "Person" .
    </output_turtle>
</example>

<example>
    <input_text>
    </input_text>
    <output_turtle>
No input provided. </output_turtle> </example> </examples> """
