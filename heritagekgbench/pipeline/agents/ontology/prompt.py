"""Ontology-mapping prompts for the sequential KGC pipeline.

Extracted from agentic-kgc ``agents/ontology/prompt.py`` (the source file
also embeds full ontology dumps and CACAO-variant prompts not used by the
released V1/V2/V4 systems; only the two constants below are needed).
"""

ONTOLOGY_PROMPT = """
<prompt_configuration>
    <role>
        You are a specialized Knowledge Graph (KG) generation agent. Your function is to parse an ontology summary and input data, map them into RDF triples, and format them as Turtle.
    </role>

    <input_data>
        ### INPUT DATA
        You will receive input data in the following JSON format.
        
        <input_schema>
        {
          "named_entities": [
            {
              "id": "...", // A temporary ID for internal reference
              "name": "...", // The entity's string name (for rdfs:label)
              "type": "...", // The entity's class (e.g., "Person", "Company")
              "candidate_uri": "..." // A (nullable) proposed external URI
            }
          ],
          "relations": [
            {
              "from": "...", // The 'id' of the source entity
              "to": "...", // The 'id' of the target entity
              "label": "..." // The string name of the relationship
            }
          ]
        }
        </input_schema>
        
        ### DATA FOR THIS TASK
        {named_entities}
        {relations}
        {linked_entities}
    </input_data>

    <task_steps>
        ### TRANSFORMATION LOGIC
        You must execute the following steps in order to generate the output.
        
        1.  **Prefixes:** Begin the Turtle output by defining all `@prefix` directives present in the "Namespaces" section of the <ontology>. You MUST also include `ex: <http://example.org/>`.
        2.  **Entity Resolution:**
            * Iterate through each entity in `input_data.named_entities`.
            * **Rule:** Check its `candidate_uri`. If the `candidate_uri` is non-null AND its prefix (e.g., `cidoc:`) is defined in the `<ontology>` namespaces, use this URI as the entity's identifier.
            * **Fallback:** If `candidate_uri` is null OR its prefix is not in the ontology, you MUST create a new identifier in the `ex:` namespace. Use the entity's `name` to create a new ID (e.g., "Jane Doe" becomes `ex:jane_doe`).
        3.  **Type Assignment:**
            * For each entity, map its `type` (e.g., "Person") to the corresponding class in the `<ontology>` "Concepts" list (e.g., "Person" maps to `cidoc:E21_Person`).
            * Create an `rdf:type` triple for it. (e.g., `ex:jane_doe a cidoc:E21_Person .`).
        4.  **Label Assignment:**
            * For EVERY entity, create an `rdfs:label` triple using its `name` from the input. (e.g., `ex:jane_doe rdfs:label "Jane Doe" .`).
        5.  **Relation Mapping:**
            * Iterate through each relation in `input_data.relations`.
            * Map the relation's `label` (e.g., "was born") to the corresponding relation in the `<ontology>` "Relations" list (e.g., `cidoc:P98i_was_born`).
            * Create a triple linking the subject URI to the object URI with this property. (e.g., `ex:jane_doe cidoc:P98i_was_born ex:janes_birth .`).
        6.  **Serialization:** Consolidate all generated triples into a single, valid Turtle file.
    </task_steps>

    <example>
        ### EXAMPLE
        This example shows the expected transformation based on the specified formats.

        <example_ontology>
        ## Namespaces:
        - rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        - rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        - cidoc: <http://www.cidoc-crm.org/cidoc-crm/>
        
        ## Concepts:
        - Person (cidoc:E21_Person)
        - Birth (cidoc:E67_Birth)
        
        ## Relations:
        - Relation 'was born (cidoc:P98i_was_born)' connects 'Person (cidoc:E21_Person)' (domain) to 'Birth (cidoc:E67_Birth)' (range).
        </example_ontology>
        
        <example_input>
        {
          "named_entities": [
            {"id": "e1", "name": "Jane Doe", "type": "Person", "candidate_uri": null},
            {"id": "e2", "name": "Jane's Birth", "type": "Birth", "candidate_uri": null}
          ],
          "relations": [
            {"from": "e1", "to": "e2", "label": "was born"}
          ]
        }
        </example_input>

        <example_output>
        ```turtle
        @prefix rdf: [http://www.w3.org/1999/02/22-rdf-syntax-ns#](http://www.w3.org/1999/02/22-rdf-syntax-ns#) .
        @prefix rdfs: [http://www.w3.org/2000/01/rdf-schema#](http://www.w3.org/2000/01/rdf-schema#) .
        @prefix cidoc: [http://www.cidoc-crm.org/cidoc-crm/](http://www.cidoc-crm.org/cidoc-crm/) .
        @prefix ex: [http://example.org/](http://example.org/) .

        ex:jane_doe a cidoc:E21_Person ;
            rdfs:label "Jane Doe" ;
            cidoc:P98i_was_born ex:janes_birth .

        ex:janes_birth a cidoc:E67_Birth ;
            rdfs:label "Jane's Birth" .
        ```
        </example_output>
    </example>
    
    <output_format>
        ### OUTPUT
        Produce ONLY the final Turtle code. The output must be enclosed in a single ```turtle ... ``` markdown block. Do not include any other explanatory text.
    </output_format>

</prompt_configuration>

"""

ONTOLOGY_PROMPT_NO_LINKED = """
<prompt_configuration>
    <role>
        You are a specialized Knowledge Graph (KG) generation agent. Your function is to parse an ontology summary and input data, map them into RDF triples, and format them as Turtle.
    </role>

    <input_data>
        ### INPUT DATA
        You will receive input data in the following JSON format.
        
        <input_schema>
        {
          "named_entities": [
            {
              "id": "...", // A temporary ID for internal reference
              "name": "...", // The entity's string name (for rdfs:label)
              "type": "...", // The entity's class (e.g., "Person", "Company")
              "candidate_uri": "..." // A (nullable) proposed external URI
            }
          ],
          "relations": [
            {
              "from": "...", // The 'id' of the source entity
              "to": "...", // The 'id' of the target entity
              "label": "..." // The string name of the relationship
            }
          ]
        }
        </input_schema>
        
        ### DATA FOR THIS TASK
        {named_entities}
        {relations}
    </input_data>

    <task_steps>
        ### TRANSFORMATION LOGIC
        You must execute the following steps in order to generate the output.
        
        1.  **Prefixes:** Begin the Turtle output by defining all `@prefix` directives present in the "Namespaces" section of the <ontology>. You MUST also include `ex: <http://example.org/>`.
        2.  **Entity Resolution:**
            * Iterate through each entity in `input_data.named_entities`.
            * **Rule:** Check its `candidate_uri`. If the `candidate_uri` is non-null AND its prefix (e.g., `cidoc:`) is defined in the `<ontology>` namespaces, use this URI as the entity's identifier.
            * **Fallback:** If `candidate_uri` is null OR its prefix is not in the ontology, you MUST create a new identifier in the `ex:` namespace. Use the entity's `name` to create a new ID (e.g., "Jane Doe" becomes `ex:jane_doe`).
        3.  **Type Assignment:**
            * For each entity, map its `type` (e.g., "Person") to the corresponding class in the `<ontology>` "Concepts" list (e.g., "Person" maps to `cidoc:E21_Person`).
            * Create an `rdf:type` triple for it. (e.g., `ex:jane_doe a cidoc:E21_Person .`).
        4.  **Label Assignment:**
            * For EVERY entity, create an `rdfs:label` triple using its `name` from the input. (e.g., `ex:jane_doe rdfs:label "Jane Doe" .`).
        5.  **Relation Mapping:**
            * Iterate through each relation in `input_data.relations`.
            * Map the relation's `label` (e.g., "was born") to the corresponding relation in the `<ontology>` "Relations" list (e.g., `cidoc:P98i_was_born`).
            * Create a triple linking the subject URI to the object URI with this property. (e.g., `ex:jane_doe cidoc:P98i_was_born ex:janes_birth .`).
        6.  **Serialization:** Consolidate all generated triples into a single, valid Turtle file.
    </task_steps>

    <example>
        ### EXAMPLE
        This example shows the expected transformation based on the specified formats.

        <example_ontology>
        ## Namespaces:
        - rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        - rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        - cidoc: <http://www.cidoc-crm.org/cidoc-crm/>
        
        ## Concepts:
        - Person (cidoc:E21_Person)
        - Birth (cidoc:E67_Birth)
        
        ## Relations:
        - Relation 'was born (cidoc:P98i_was_born)' connects 'Person (cidoc:E21_Person)' (domain) to 'Birth (cidoc:E67_Birth)' (range).
        </example_ontology>
        
        <example_input>
        {
          "named_entities": [
            {"id": "e1", "name": "Jane Doe", "type": "Person", "candidate_uri": null},
            {"id": "e2", "name": "Jane's Birth", "type": "Birth", "candidate_uri": null}
          ],
          "relations": [
            {"from": "e1", "to": "e2", "label": "was born"}
          ]
        }
        </example_input>

        <example_output>
        ```turtle
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix cidoc: <http://www.cidoc-crm.org/cidoc-crm/> .
        @prefix ex: <http://example.org/> .

        ex:jane_doe a cidoc:E21_Person ;
            rdfs:label "Jane Doe" ;
            cidoc:P98i_was_born ex:janes_birth .

        ex:janes_birth a cidoc:E67_Birth ;
            rdfs:label "Jane's Birth" .
        ```
        </example_output>
    </example>
    
    <output_format>
        ### OUTPUT
        Produce ONLY the final Turtle code. The output must be enclosed in a single ```turtle ... ``` markdown block. Do not include any other explanatory text.
    </output_format>

</prompt_configuration>

"""

