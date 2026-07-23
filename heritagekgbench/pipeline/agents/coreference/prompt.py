COREFERENCE_RESOLUTION_PROMPT = """
<task_definition>
Your task is to perform coreference resolution on the provided text.
1.  Identify all mentions (names, pronouns, noun phrases) that refer to the same real-world entity.
2.  Group these mentions into a list.
3.  Return a JSON list containing all groups.
</task_definition>

<output_specification>
-   The output must be a valid JSON list of lists.
-   Each inner list must contain the string mentions for a single entity.
-   The strings must be an *exact match* of the text from the input.
-   If no coreferences are found, return an empty list `[]`.
-   DO NOT output any text, explanation, or commentary outside the JSON block.
</output_specification>

<examples>
    <example>
        <input_text>
Dr. Evelyn Reed discovered the comet. She reported her findings to the observatory, which praised Reed for the discovery.
        </input_text>
        <output_json>
[
  ["Dr. Evelyn Reed", "She", "her", "Reed"]
]
        </output_json>
    </example>

    <example>
        <input_text>
The old library on Main Street is being demolished. It was a beloved landmark. The city council, however, said they needed the land for a new park.
        </input_text>
        <output_json>
[
  ["The old library on Main Street", "It", "a beloved landmark"],
  ["The city council", "they"]
]
        </output_json>
    </example>

    <example>
        <input_text>
The sky is blue and the grass is green.
        </input_text>
        <output_json>
[]
        </output_json>
    </example>
</examples>

"""
