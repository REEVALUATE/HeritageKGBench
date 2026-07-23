import json
import logging
from typing import Dict, Optional

from bs4 import BeautifulSoup
from google.adk.tools import ToolContext
import logging

logger = logging.getLogger(__name__)
import pandas as pd
import requests


def make_get_request(
    url: str, params: Optional[Dict] = None, headers: Optional[Dict] = None, timeout: int = 30
) -> requests.Response:
    """
    Performs a GET request to a specified URL with optional query parameters and headers.

    Args:
        url (str): The URL endpoint to send the GET request to.
        params (Optional[Dict], optional): A dictionary of query parameters to append to the URL.
                                            Defaults to None.
        headers (Optional[Dict], optional): A dictionary of HTTP headers to send with the request.
                                             Defaults to None.
        timeout (int, optional): The maximum number of seconds to wait for a response.
                                 Defaults to 30.

    Returns:
        requests.Response: The response object from the GET request.

    Raises:
        requests.exceptions.RequestException: If an error occurs during the request
                                              (e.g., connection error, timeout).
    """
    try:
        if headers is None:
            headers = {
                "User-Agent": "REEVALUATEBot/0.0 (https://reevaluate.eu/; ruben.peeters@kuleuven.be)"
            }
        else:
            headers["User-Agent"] = (
                "REEVALUATEBot/0.0 (https://reevaluate.eu/; ruben.peeters@kuleuven.be)"
            )

        logger.info(f"Sending GET request to: {url}")
        if params:
            logger.info(f"Request parameters: {params}")

        response = requests.get(url, params=params, headers=headers, timeout=timeout)

        # Raise an HTTPError for bad responses (4xx or 5xx)
        response.raise_for_status()

        logger.info(f"GET request successful! Status Code: {response.status_code}")
        # logger.debug(f"Response content: {response.text}")

        return response

    except requests.exceptions.Timeout:
        logger.error(f"Error: The request timed out after {timeout} seconds.")
        raise
    except requests.exceptions.ConnectionError:
        logger.error(
            "Error: A connection error occurred. Please check the URL or your network connection."
        )
        raise
    except requests.exceptions.HTTPError as e:
        logger.error(f"Error: HTTP error occurred - {e.response.status_code} {e.response.reason}")
        logger.error(f"Response content: {e.response.text}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"An unexpected request error occurred: {e}")
        raise


def get_concepts_from_aat(query: str) -> str:
    curl_url = f"http://vocab.getty.edu/resource/getty/search?q={query}&luceneIndex=Brief&indexDataset=Any&_form=%2Fresource%2Fgetty%2Fsearch"

    try:
        response_curl = make_get_request(curl_url)
        # logger.info(f"Curl command translation response status: {response_curl.status_code}")
        # logger.debug(f"Curl command translation response body: {response_curl.text}")
        return response_curl.text

    except requests.exceptions.RequestException as e:
        logger.error(f"Curl command translation failed: {e}")
        return ""


def extract_table_data(html_content: str) -> dict:
    """
    Parses HTML content to extract data from a table and returns it as a dictionary.

    Args:
        html_content (str): The HTML content (as a string) to parse.

    Returns:
        dict: A dictionary containing the extracted table data.
                      Returns an empty dictionary if no table is found.
    """
    try:
        soup = BeautifulSoup(html_content, "lxml")
        table = soup.find("table", class_="table-striped")

        if not table:
            logger.warning("No table with class 'table-striped' found in the HTML content.")
            return dict()

        # Use pandas to read the HTML table directly
        # This is often the most efficient way to handle well-formed tables
        df = pd.read_html(str(table))[0]

        logger.success("Successfully extracted table data into a DataFrame.")
        return json.loads(df.to_json(orient="records", indent=2))

    except Exception as e:
        logger.error(f"An error occurred during HTML parsing: {e}")
        return json.loads(pd.DataFrame().to_json(orient="records", indent=2))


def get_concepts_from_wikidata(query: str) -> str:
    curl_url = f"https://www.wikidata.org/w/index.php?language=en&search={query}&title=Special%3ASearch&fulltext=1&ns0=1"

    try:
        response_curl = make_get_request(curl_url)
        # logger.info(f"Curl command translation response status: {response_curl.status_code}")
        # logger.debug(f"Curl command translation response body: {response_curl.text}")
        # print(response_curl.text)
        return response_curl.text
        # bindings = json.loads(response_curl.text)["results"]["bindings"]

        # Create an empty list to store the tuples

        # Iterate through each binding and extract the label and URI
        # for item in bindings:
        #     label = item["label"]["value"]
        #     uri = item["entity"]["value"]
        #     list_of_tuples.append((label, uri))
    except requests.exceptions.RequestException as e:
        logger.error(f"Curl command translation failed: {e}")
        return ""
    # return list_of_tuples


def extract_search_results(html_content):
    """
    Parses HTML content to extract search results from a MediaWiki-like structure.

    Args:
        html_content (str): A string containing the HTML of the search results page.

    Returns:
        list: A list of dictionaries, where each dictionary represents a search result.
              Returns an empty list if the container is not found or no results are present.
    """
    # Create a BeautifulSoup object to parse the HTML.
    # We're using the 'lxml' parser, which is fast and robust.
    soup = BeautifulSoup(html_content, "lxml")

    # Find the main container for the search results.
    results_container = soup.find("div", class_="mw-search-results-container")

    # Initialize a list to store our extracted results.
    extracted_results = []

    # Check if the container was found before trying to search within it.
    if not results_container:
        print("Could not find the 'mw-search-results-container' div.")
        return extracted_results  # Return empty list if container is missing

    # Find all list items ('li') within the container. These typically represent individual search results.
    search_items = results_container.find_all("li")

    # Loop through each found list item to extract the details.
    for item in search_items:
        # Find the heading div and then the 'a' tag within it to get the title and link.
        heading_link = item.find("div", class_="mw-search-result-heading").find("a")

        # Find the snippet/description of the result.
        snippet = item.find("div", class_="searchresult")

        # Check if the elements exist before trying to access their attributes/text
        if heading_link and snippet:
            title = heading_link.get_text(strip=True)
            link = heading_link.get(
                "href", "No link found"
            )  # Use .get() for safe attribute access
            description = snippet.get_text(strip=True)

            # Store the extracted data in a dictionary for clarity.
            extracted_results.append(
                {
                    "title": title,
                    "link": f"https://www.wikidata.org{link}",
                    "description": description,
                }
            )

    return extracted_results


def search_aat(tool_context: ToolContext) -> dict:
    """
    Searches the Getty AAT returns a dictionary of results.
    Args:
        None

    Returns:
        dict: A dictionary containing entries found in Wikidata with fields: 'label' and 'uri'.
    """
    try:
        pre_processed_text = (
            tool_context.state.get("named_entities").replace("```json\n", "").replace("\n```", "")
        )
        entities = json.loads(pre_processed_text)
    except Exception:
        logging.debug(tool_context.state.get("named_entities"))
        logging.exception("Failed to load named entities from tool context.")
        return dict()
    out = dict()
    if not entities:
        logger.warning("No named entities found in the tool context state.")
        return out
    for e in entities:
        html_content = get_concepts_from_aat(e["entity"])
        res = extract_table_data(html_content)
        if res:
            if len(res) > 5:
                out[e["entity"]] = res[:5]
            else:
                out[e["entity"]] = res
        else:
            logger.warning(f"No results found for entity: {e['entity']}")
    return out


def search_wikidata(tool_context: ToolContext) -> dict:
    """
    Searches Wikidata for concepts and returns a dictionary of results.

    Args:
        None

    Returns:
        dict: A dictionary of dictionaries containing entries found in Wikidata with fields: 'title', 'link', and 'description.
    """
    try:
        pre_processed_text = (
            tool_context.state.get("named_entities").replace("```json\n", "").replace("\n```", "")
        )
        entities = json.loads(pre_processed_text)
    except Exception:
        logging.error("Failed to load named entities from tool context.")
        logging.error(tool_context.state.get("named_entities"))
        logging.exception("Failed to load named entities from tool context.")
        return dict()
    out = dict()
    if not entities:
        logger.warning("No named entities found in the tool context state.")
        return out
    for e in entities:
        html_content = get_concepts_from_wikidata(e["entity"])
        res = extract_search_results(html_content)
        if res:
            if len(res) > 5:
                out[e["entity"]] = res[:5]
            else:
                out[e["entity"]] = res
        else:
            logger.warning(f"No results found for entity: {e['entity']}")
    return out
