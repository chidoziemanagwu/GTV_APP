// expert_marketplace/static/js/admin/expert_admin.js
document.addEventListener('DOMContentLoaded', function() {
    // Format the JSON in the availability field when the page loads
    const availabilityField = document.querySelector('.availability-editor');
    if (availabilityField && availabilityField.value) {
        try {
            const availabilityData = JSON.parse(availabilityField.value);
            availabilityField.value = JSON.stringify(availabilityData, null, 2);
        } catch (e) {
            // If it's not valid JSON, leave it as is
            console.log('Could not parse availability JSON');
        }
    }
});