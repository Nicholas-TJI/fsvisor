import logging
import os
import random
import time

import pandas as pd
import requests
from dotenv import find_dotenv, load_dotenv


class FormSiteClient:
    def __init__(
        self,
        realm_hostname: str = None,
        api_key: str = None,
        user_id: str = None,
        logger=None,
        load_env: bool = True,
    ):
        # Load a .env file from the working directory (or its parents) without overriding real env vars
        if load_env:
            load_dotenv(find_dotenv(usecwd=True), override=False)

        # Explicit arguments win, environment variables are the fallback
        self.realm_hostname = realm_hostname or os.getenv('FORMSITE_REALM_HOSTNAME')
        self.authorization = api_key or os.getenv('FORMSITE_API_KEY')
        self.user_id = user_id or os.getenv('FORMSITE_USER_ID')

        # Store the authorization in headers for API requests
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': self.authorization
        }
        self.logger = logger or logging.getLogger("fsvisor")

    def _log(self, level: str, message: str):
        getattr(self.logger, level, self.logger.info)(message)

    ### Getter Setter Methods ###
    @property
    def realm_hostname(self):
        return self._realm_hostname

    @realm_hostname.setter
    def realm_hostname(self, realm_hostname):
        # If the variable is empty or None, raise an error
        if not realm_hostname:
            raise ValueError('Realm hostname cannot be empty or None')
        # If the variable is not a string or does not follow the format of server.formsite.com, raise an error
        elif not isinstance(realm_hostname, str) or len(realm_hostname.split('.')) != 3:
            raise ValueError('Realm hostname must be a string and follow the format of server.formsite.com')
        else:
            # Set the realm_hostname if all checks pass
            self._realm_hostname = realm_hostname

    @property
    def authorization(self):
        return self._authorization

    @authorization.setter
    def authorization(self, authorization):
        # If the variable is empty or None, raise an error
        if not authorization:
            raise ValueError('Authorization token cannot be empty or None')
        # If the variable is not a string, raise an error
        elif not isinstance(authorization, str):
            raise ValueError('Authorization token must be a string')
        else:
            # Formsite expects a bearer token, so add the prefix if it was left off
            authorization = authorization.strip()
            if not authorization.lower().startswith('bearer'):
                authorization = f'Bearer {authorization}'
            self._authorization = authorization

    @property
    def user_id(self):
        return self._user_id

    @user_id.setter
    def user_id(self, user_id):
        # If the variable is empty or None, raise an error
        if not user_id:
            raise ValueError('User ID cannot be empty or None')
        # If the variable is not a string, raise an error
        elif not isinstance(user_id, str):
            raise ValueError('User ID must be a string')
        else:
            # Set the user ID if all checks pass
            self._user_id = user_id

    ### Generic Request Methods ###
    @staticmethod
    def _is_retryable(error: requests.exceptions.RequestException) -> bool:
        # Only rate limits and server-side errors can succeed on a retry; other 4xx errors
        # (bad credentials, unknown form, bad parameters) will fail the same way every time
        if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
            status = error.response.status_code
            return status == 429 or status >= 500
        # Connection errors and timeouts are transient
        return isinstance(error, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))

    def _make_request(self, method, url, params=None, body=None):
        # Set parameters for backoff retry
        max_attempts = 5 # Maximum number of attempts
        base_delay = 1 # Initial delay in seconds
        max_delay = 64 # Maximum delay in seconds
        delay = base_delay

        # Retry loop
        for attempt in range(max_attempts):
            try:
                # Make the request using the provided method
                response = method(url, params=params, json=body, headers=self.headers)
                response.raise_for_status() # Raise an exception for 4xx or 5xx errors
                return response # Return the response if successful
            except requests.exceptions.RequestException as e:
                if not self._is_retryable(e):
                    self._log('error', f"Request failed with a non-retryable error: {e}")
                    raise
                if attempt == max_attempts - 1:
                    self._log('error', f"Max attempts reached. Last Exception: {e}")
                    raise
                # Calculate delay with jitter
                jitter = random.uniform(0.5, 1.5) # Random jitter between 0.5 and 1.5
                delay_with_jitter = delay * jitter # Delay multiplied by jitter
                self._log('warning', f"Attempt {attempt + 1} failed. Retrying in {delay_with_jitter} seconds.")
                time.sleep(delay_with_jitter) # Sleep for the calculated delay
                delay = min(max_delay, delay * 2) # Exponential backoff with max delay

    ### URL Construction Methods ###
    def _construct_url(self, endpoint):
        base_url = f'https://{self.realm_hostname}/api/v2/{self.user_id}/forms/'
        return f'{base_url}{endpoint}'

    ### API Methods ###
    def get_form_results(
            self,
            form_id: str,
            results_view: int = 10,
            page: int = 1,
            limit: int = 100,
            before_date: str = None,
            after_date: str = None,
            sort_direction: str = 'desc',
            ) -> list:
        """
        Fetch results from the Formsite API for a specific page and limit.
        Args:
            form_id (str): The form ID for which results are to be fetched.
            results_view (int): The results view to fetch (Each export has a specific ID with 10 being all items and personal views being 3 digits).
            page (int): The page number of results to fetch.
            limit (int): The number of results to fetch per page.
            before_date (str): The date before which results are to be fetched in either ISO 8601 UTC or YYYY-MM-DD HH:MM:SS local date.
            after_date (str): The date after which results are to be fetched in either ISO 8601 or YYYY-MM-DD HH:MM:SS local date.
            sort_direction (str): The direction in which to sort the results (asc or desc).
        Returns:
            list: A list of dictionaries containing the results for the form.
        Raises:
            requests.exceptions.RequestException: If the request fails and cannot be retried.
        """
        # Set the URL for the API request
        url = self._construct_url(f'{form_id}/results')

        # Set parameters for the API request
        params = {
            'results_view': results_view,
            'page': page,
            'limit': limit
        }

        # Add date filters if provided
        if before_date:
            params['before_date'] = before_date
        if after_date:
            params['after_date'] = after_date

        # Add sort direction if provided
        if sort_direction:
            params['sort_direction'] = sort_direction

        # Make the API request
        response = self._make_request(requests.get, url, params=params)

        # Return the 'results' part of the JSON response
        return response.json().get('results', [])

    def get_form_metadata(self, form_id: str, results_labels: int = None) -> dict:
        """
        Fetch metadata for a specific form from the Formsite API.
        Args:
            form_id (str): The form ID for which metadata is to be fetched.
            results_labels (int): The results labels to fetch metadata for.
        Returns:
            dict: A mapping of item IDs to their labels.
        Raises:
            requests.exceptions.RequestException: If the request fails and cannot be retried.
        """
        # Set the URL for the API request
        url = self._construct_url(f'{form_id}/items')

        # Set parameters for the API request
        params = {}

        # Add results labels if provided
        if results_labels:
            params['results_labels'] = results_labels

        # Make the API request
        response = self._make_request(requests.get, url, params=params)

        # Return the 'items' part of the JSON response
        items = response.json().get('items', [])
        return {item['id']: item['label'] for item in items}

    def get_results_dataframe(
        self,
        form_id: str,
        results_view: int,
        limit_per_request: int = 100,
        before_date: str = None,
        after_date: str = None,
        sort_direction: str = 'desc',
        results_labels: int = None
        ) -> pd.DataFrame:
        """
        Fetch results and return as a labeled pandas DataFrame with dynamic pagination.

        Args:
            form_id (str): The form ID for which results are to be fetched.
            results_view (int): The results view to fetch.
            limit_per_request (int): The number of records to fetch per request.
            before_date (str): The date before which results are to be fetched.
            after_date (str): The date after which results are to be fetched.
            sort_direction (str): The direction in which to sort the results.
            results_labels (int): The number of the labels to fetch for the results.

        Returns:
            pd.DataFrame: A labeled DataFrame containing the results.

        Raises:
            requests.exceptions.RequestException: If any page or the metadata request fails and cannot be retried.
        """
        all_results = []
        page = 1

        # Fetch all results dynamically until no more results are returned
        while True:
            self._log('info', f"Fetching page {page} with limit {limit_per_request}...")
            results = self.get_form_results(
                form_id,
                results_view,
                page=page,
                limit=limit_per_request,
                before_date=before_date,
                after_date=after_date,
                sort_direction=sort_direction
            )

            if not results:
                break  # Exit if no results are returned

            all_results.extend(results)

            if len(results) < limit_per_request:
                break  # Exit if the current page has fewer than the limit

            page += 1

        # Process the results into rows
        processed_rows = []
        for result in all_results:
            row = {}
            for item in result.get('items', []):
                col_id = str(item['id'])
                if 'value' in item:
                    row[col_id] = item['value']
                elif 'values' in item and item['values']:
                    row[col_id] = "; ".join(v['value'] for v in item['values'])
                else:
                    row[col_id] = None
            processed_rows.append(row)

        # Convert processed rows to a DataFrame
        df = pd.DataFrame(processed_rows)

        # Apply metadata to the DataFrame for column renaming
        metadata = self.get_form_metadata(form_id, results_labels)
        if metadata:
            df.rename(columns=metadata, inplace=True)
        else:
            self._log('warning', f'No metadata found for form ID: {form_id}')

        return df
