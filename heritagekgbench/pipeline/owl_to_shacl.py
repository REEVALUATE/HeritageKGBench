"""
OWL to SHACL Converter for Domain-Specific Validation.

This module converts OWL ontology constraints to SHACL shapes for validation.
Supports multiple conversion strategies:
1. Direct OWL2SHACL conversion (if available)
2. SCOOP-style conversion (lightweight, built-in)
3. Manual constraint extraction from OWL axioms

"""

from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

# SHACL namespace
SH = Namespace("http://www.w3.org/ns/shacl#")


class OWLToSHACLConverter:
    """
    Converts OWL ontology to SHACL shapes for validation.

    This converter extracts constraints from OWL axioms and generates
    equivalent SHACL shapes. It handles:
    - Domain and range constraints
    - Cardinality restrictions
    - Property restrictions
    - Class hierarchies
    """

    def __init__(self, ontology_path: str):
        """
        Initialize converter with OWL ontology.

        Args:
            ontology_path: Path to OWL/RDF ontology file
        """
        self.ontology_path = Path(ontology_path)
        self.ontology_graph = Graph()
        self.shapes_graph = Graph()

        # Bind namespaces
        self.shapes_graph.bind("sh", SH)
        self.shapes_graph.bind("rdf", RDF)
        self.shapes_graph.bind("rdfs", RDFS)
        self.shapes_graph.bind("owl", OWL)
        self.shapes_graph.bind("xsd", XSD)

        # Load ontology
        self._load_ontology()

    def _load_ontology(self):
        """Load and parse the OWL ontology."""
        try:
            self.ontology_graph.parse(str(self.ontology_path))
            logger.info(f"Loaded ontology: {len(self.ontology_graph)} triples")

            # Extract ontology namespace
            self.ontology_namespace = self._extract_ontology_namespace()
            if self.ontology_namespace:
                self.shapes_graph.bind("onto", self.ontology_namespace)

        except Exception as e:
            logger.error(f"Failed to load ontology: {e}")
            raise

    def _extract_ontology_namespace(self) -> Optional[Namespace]:
        """Extract the main ontology namespace."""
        # Try to find ontology declaration
        for s, p, o in self.ontology_graph.triples((None, RDF.type, OWL.Ontology)):
            namespace_str = str(s)
            if not namespace_str.endswith("/") and not namespace_str.endswith("#"):
                namespace_str += "#"
            return Namespace(namespace_str)

        # Fallback: use first non-standard namespace
        for prefix, namespace in self.ontology_graph.namespaces():
            if prefix not in ["rdf", "rdfs", "owl", "xsd", "skos", "sh"]:
                return namespace

        return None

    def convert(self) -> str:
        """
        Convert OWL ontology to SHACL shapes.

        Returns:
            SHACL shapes as Turtle string
        """
        logger.info("Converting OWL to SHACL shapes...")

        # Step 1: Extract classes and create node shapes
        self._convert_classes()

        # Step 2: Extract object properties and constraints
        self._convert_object_properties()

        # Step 3: Extract datatype properties
        self._convert_datatype_properties()

        # Step 4: Extract cardinality restrictions
        self._convert_restrictions()

        # Serialize to Turtle
        shapes_turtle = self.shapes_graph.serialize(format="turtle")
        logger.info(f"Generated SHACL shapes: {len(self.shapes_graph)} triples")

        return shapes_turtle

    def _convert_classes(self):
        """Convert OWL classes to SHACL node shapes."""
        for class_uri in self.ontology_graph.subjects(RDF.type, OWL.Class):
            if isinstance(class_uri, BNode):
                continue  # Skip blank nodes

            # Create a node shape for this class
            shape_uri = URIRef(str(class_uri) + "Shape")

            self.shapes_graph.add((shape_uri, RDF.type, SH.NodeShape))
            self.shapes_graph.add((shape_uri, SH.targetClass, class_uri))

            # Add label if available
            for label in self.ontology_graph.objects(class_uri, RDFS.label):
                self.shapes_graph.add((shape_uri, RDFS.label, Literal(f"Shape for {label}")))

            logger.debug(f"Created node shape for class: {class_uri}")

    def _convert_object_properties(self):
        """Convert OWL object properties to SHACL property shapes."""
        for prop_uri in self.ontology_graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(prop_uri, BNode):
                continue

            # Get domain and range
            domains = list(self.ontology_graph.objects(prop_uri, RDFS.domain))
            ranges = list(self.ontology_graph.objects(prop_uri, RDFS.range))

            for domain in domains:
                if isinstance(domain, BNode):
                    continue

                # Create property shape
                domain_shape = URIRef(str(domain) + "Shape")
                property_shape = BNode()

                self.shapes_graph.add((domain_shape, SH.property, property_shape))
                self.shapes_graph.add((property_shape, SH.path, prop_uri))

                # Add range constraint (sh:class)
                if ranges:
                    for range_class in ranges:
                        if not isinstance(range_class, BNode):
                            self.shapes_graph.add((property_shape, SH["class"], range_class))

                # Add property name
                for label in self.ontology_graph.objects(prop_uri, RDFS.label):
                    self.shapes_graph.add((property_shape, SH.name, label))

                logger.debug(f"Created property shape for: {prop_uri}")

    def _convert_datatype_properties(self):
        """Convert OWL datatype properties to SHACL property shapes."""
        for prop_uri in self.ontology_graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(prop_uri, BNode):
                continue

            domains = list(self.ontology_graph.objects(prop_uri, RDFS.domain))
            ranges = list(self.ontology_graph.objects(prop_uri, RDFS.range))

            for domain in domains:
                if isinstance(domain, BNode):
                    continue

                domain_shape = URIRef(str(domain) + "Shape")
                property_shape = BNode()

                self.shapes_graph.add((domain_shape, SH.property, property_shape))
                self.shapes_graph.add((property_shape, SH.path, prop_uri))

                # Add datatype constraint
                if ranges:
                    for datatype in ranges:
                        if not isinstance(datatype, BNode):
                            self.shapes_graph.add((property_shape, SH.datatype, datatype))

                logger.debug(f"Created datatype property shape for: {prop_uri}")

    def _convert_restrictions(self):
        """
        Convert OWL restrictions to SHACL cardinality constraints.

        Handles:
        - owl:minCardinality → sh:minCount
        - owl:maxCardinality → sh:maxCount
        - owl:cardinality → sh:minCount + sh:maxCount
        - owl:someValuesFrom → sh:minCount 1
        - owl:allValuesFrom → sh:class constraint
        """
        # Find all restriction classes
        for restriction in self.ontology_graph.subjects(RDF.type, OWL.Restriction):
            # Get the property being restricted
            on_property = self.ontology_graph.value(restriction, OWL.onProperty)
            if not on_property:
                continue

            # Find which class has this restriction
            for class_uri in self.ontology_graph.subjects(RDFS.subClassOf, restriction):
                if isinstance(class_uri, BNode):
                    continue

                domain_shape = URIRef(str(class_uri) + "Shape")

                # Create property shape for the restriction
                property_shape = BNode()
                self.shapes_graph.add((domain_shape, SH.property, property_shape))
                self.shapes_graph.add((property_shape, SH.path, on_property))

                # Extract cardinality constraints
                min_card = self.ontology_graph.value(restriction, OWL.minCardinality)
                max_card = self.ontology_graph.value(restriction, OWL.maxCardinality)
                exact_card = self.ontology_graph.value(restriction, OWL.cardinality)

                if min_card:
                    self.shapes_graph.add((property_shape, SH.minCount, min_card))
                    logger.debug(f"Added minCount {min_card} for {on_property}")

                if max_card:
                    self.shapes_graph.add((property_shape, SH.maxCount, max_card))
                    logger.debug(f"Added maxCount {max_card} for {on_property}")

                if exact_card:
                    self.shapes_graph.add((property_shape, SH.minCount, exact_card))
                    self.shapes_graph.add((property_shape, SH.maxCount, exact_card))
                    logger.debug(f"Added exact cardinality {exact_card} for {on_property}")

                # Handle someValuesFrom (existential restriction)
                some_values = self.ontology_graph.value(restriction, OWL.someValuesFrom)
                if some_values:
                    self.shapes_graph.add((property_shape, SH.minCount, Literal(1)))
                    if not isinstance(some_values, BNode):
                        self.shapes_graph.add((property_shape, SH["class"], some_values))

                # Handle allValuesFrom (universal restriction)
                all_values = self.ontology_graph.value(restriction, OWL.allValuesFrom)
                if all_values and not isinstance(all_values, BNode):
                    self.shapes_graph.add((property_shape, SH["class"], all_values))


def convert_ontology_to_shacl(ontology_path: str) -> str:
    """
    Convert OWL ontology to SHACL shapes.

    This is the main entry point for OWL to SHACL conversion.

    Args:
        ontology_path: Path to OWL/RDF ontology file

    Returns:
        SHACL shapes as Turtle string
    """
    converter = OWLToSHACLConverter(ontology_path)
    return converter.convert()


def save_shacl_shapes(ontology_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert ontology to SHACL and save to file.

    Args:
        ontology_path: Path to OWL/RDF ontology file
        output_path: Optional output path (default: ontology_path with .shacl.ttl suffix)

    Returns:
        Path to saved SHACL file
    """
    shapes_turtle = convert_ontology_to_shacl(ontology_path)

    if output_path is None:
        ontology_file = Path(ontology_path)
        output_path = ontology_file.parent / f"{ontology_file.stem}.shacl.ttl"

    output_path = Path(output_path)
    output_path.write_text(shapes_turtle)

    logger.info(f"Saved SHACL shapes to: {output_path}")
    return str(output_path)


# Example usage for Text2KGBench ontologies
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python owl_to_shacl.py <ontology_path> [output_path]")
        sys.exit(1)

    ontology_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    saved_path = save_shacl_shapes(ontology_path, output_path)
    print(f"✓ SHACL shapes saved to: {saved_path}")
