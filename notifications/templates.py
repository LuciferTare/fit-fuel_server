"""
Notification message templates.

Placeholders use Python str.format() syntax: {variable_name}.
All templates must be rendered via notifications.services.render_message().
"""

TEMPLATES: dict[str, str] = {
    # Sent when a member's membership is about to expire
    "membership_expiry": (
        "Hi {name}, your membership at {gym_name} expires on {expiry_date} "
        "({days_left} day(s) left). Please renew to keep training with us."
    ),

    # Sent when membership has already expired
    "membership_expired": (
        "Hi {name}, your membership at {gym_name} expired on {expiry_date}. "
        "Please renew your membership to continue your fitness journey."
    ),

    # Sent when a member has been absent for too many days
    "absent_reminder": (
        "Hi {name}, we miss you at {gym_name}! "
        "You haven't visited in {days} day(s). Come back and keep going strong!"
    ),

    # Sent after a payment is recorded
    "payment_received": (
        "Hi {name}, we received a payment of Rs. {amount} at {gym_name}. "
        "Your membership is now active till {end_date}. Thank you!"
    ),

    # Sent when a new member joins the gym
    "welcome_member": (
        "Welcome to {gym_name}, {name}! "
        "Your trainer is {trainer_name}. We look forward to your fitness journey with us!"
    ),

    # Sent when a member is assigned or reassigned to a trainer
    "trainer_assigned": (
        "Hi {name}, you have been assigned to trainer {trainer_name} at {gym_name}. "
        "Reach out to your trainer for your personalised schedule."
    ),
}
