# locustfile.py
import time
from locust import HttpUser, task, between, tag

# --- Configuration ---
# Replace with your actual user credentials for testing logged-in areas
TEST_USERNAME = "testuser@example.com"
TEST_PASSWORD = "yourtestpassword" # Make sure this user exists in your DB

# Replace with an actual expert ID and other relevant IDs from your DB for testing
EXISTING_EXPERT_ID = 1
EXISTING_CV_ID = 1 # Assuming a CV document ID for testing AI tools
EXISTING_PS_ID = 1 # Assuming a Personal Statement document ID

class AuthenticatedUserBehavior(HttpUser):
    wait_time = between(1, 5)  # Wait 1-5 seconds between tasks
    login_token = None
    csrftoken = None

    def on_start(self):
        """
        Called when a Locust user starts.
        This is where you'd typically log in.
        """
        self.login()

    def get_csrf_token(self, path="/accounts/login/"):
        """Helper to get CSRF token from a form page."""
        response = self.client.get(path)
        if response.status_code == 200 and "csrftoken" in response.cookies:
            self.csrftoken = response.cookies["csrftoken"]
        elif "csrfmiddlewaretoken" in response.text:
            # Fallback if not in cookies (e.g. from form hidden input)
            try:
                self.csrftoken = response.text.split('name="csrfmiddlewaretoken" value="')[1].split('"')[0]
            except IndexError:
                print(f"Could not extract CSRF token from {path}")
                self.csrftoken = None
        else:
            print(f"Could not get CSRF token from {path}. Status: {response.status_code}")
            self.csrftoken = None
        return self.csrftoken

    def login(self):
        if not self.csrftoken:
            self.get_csrf_token("/accounts/login/") # Get CSRF from login page

        if self.csrftoken:
            login_payload = {
                "username": TEST_USERNAME, # Or 'email' depending on your login form
                "password": TEST_PASSWORD,
                "csrfmiddlewaretoken": self.csrftoken
            }
            response = self.client.post("/accounts/login/", login_payload, headers={"X-CSRFToken": self.csrftoken})

            # Handle 302 redirect as success for login
            if response.status_code == 200 or (response.status_code == 302 and response.is_redirect):
                print(f"User {TEST_USERNAME} login POST successful (status: {response.status_code}).")
                if "sessionid" in self.client.cookies:
                    print("Session ID found in cookies.")
                else:
                    print("Session ID NOT found in cookies after successful login POST. Check redirects/cookie settings.")
            else:
                print(f"Login failed for {TEST_USERNAME}. Status: {response.status_code}, Response: {response.text[:500]}")
        else:
            print("Cannot login: CSRF token not found.")


    @task(10) # Higher weight means this task runs more often
    @tag("dashboard")
    def view_dashboard(self):
        self.client.get("/accounts/dashboard/")

    @task(5)
    @tag("ai_tools", "cv_scan")
    def use_cv_scanner(self):
        self.client.get("/documents/cv/analyze/")

    @task(3)
    @tag("ai_tools", "ps_generator")
    def use_ps_generator(self):
        self.client.get("/documents/personal-statement/generate/")

    # --- TASKS COMMENTED OUT BECAUSE THEIR URLS DON'T EXIST IN expert_marketplace.urls ---
    # @task(2)
    # @tag("expert_marketplace")
    # def view_experts(self):
    #     # This URL /consultation/ currently leads to a 404
    #     # because expert_marketplace/urls.py has no root path ('') defined.
    #     self.client.get("/consultation/")

    # @task(1)
    # @tag("expert_marketplace", "booking")
    # def view_expert_profile(self):
    #     # This URL /consultation/profile/ID/ currently leads to a 404
    #     # because expert_marketplace/urls.py has no 'profile/<id>/' path defined.
    #     self.client.get(f"/consultation/profile/{EXISTING_EXPERT_ID}/")
    # --- END OF COMMENTED OUT TASKS ---

    # Consider adding tasks that DO exist in your expert_marketplace flow, for example:
    @task(2) # Example: Add a task to view the "book consultation" page
    @tag("expert_marketplace", "booking_flow")
    def view_book_consultation_page(self):
        # This URL should exist based on your expert_marketplace/urls.py
        # path('book/', views.book_consultation, name='book_consultation')
        # and main urls.py: path('consultation/', include('expert_marketplace.urls'))
        self.client.get("/consultation/book/")


class UnauthenticatedUserBehavior(HttpUser):
    wait_time = between(1, 3)

    @task(10)
    @tag("general")
    def view_homepage(self):
        self.client.get("/")

    @task(5)
    @tag("general", "auth")
    def view_login_page(self):
        self.client.get("/accounts/login/")

    @task(5)
    @tag("general", "auth")
    def view_signup_page(self):
        self.client.get("/accounts/signup/")

    # --- TASK COMMENTED OUT BECAUSE ITS URL LIKELY DOESN'T EXIST ---
    # @task(2)
    # @tag("general")
    # def view_public_expert_listing(self):
    #     # This URL /consultation/ currently leads to a 404
    #     # because expert_marketplace/urls.py has no root path ('') defined.
    #     self.client.get("/consultation/")
    # --- END OF COMMENTED OUT TASK ---

    # If you have a different public page for experts, add it here.
    # For example, if the booking page is public:
    @task(2)
    @tag("general", "expert_info")
    def view_public_booking_page(self):
        # Assuming /consultation/book/ is publicly accessible
        self.client.get("/consultation/book/")