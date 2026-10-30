
"""Routes for browsing and filtering skills in the marketplace."""

from flask import Blueprint, render_template, request
from app.models import Listing, Skill


# Keep the skills feature separate from the rest of the application.
# The team can register this Blueprint in the main Flask app.
skills = Blueprint("skills", __name__)


@skills.route("/skills", methods=["GET"])
def browse():
    """
    Display the skills directory and apply any filters selected by the user.

    Users can search for a skill by name, choose between teaching and
    learning listings, or use both filters together. If no filters are
    provided, the page shows all active listings.
    """

    # Read the search values from the URL.
    # For example: /skills?keyword=python&type=teach
    # strip() removes extra spaces, and lower() makes the type consistent.
    keyword = request.args.get("keyword", "").strip()
    listing_type = request.args.get("type", "").strip().lower()

    # Start with active listings only. Joining Skill lets us search
    # by the skill's name, which is stored in a separate database table.
    query = Listing.query.join(Skill).filter(
        Listing.is_active.is_(True)
    )

    # If the user enters a keyword, find skill names containing that text.
    # ilike() ignores capitalization, so "python" also matches "Python".
    if keyword:
        query = query.filter(Skill.name.ilike(f"%{keyword}%"))

    # Only filter by type if the user selected a valid option.
    # Without a type filter, both teaching and learning listings appear.
    if listing_type in ("teach", "learn"):
        query = query.filter(Listing.type == listing_type)

    # Sort by skill name, then listing ID, so results appear consistently.
    # all() runs the query and returns the matching listings.
    listings = query.order_by(Skill.name, Listing.id).all()

    # Send the results and current filters to the HTML template.
    # The template will display the listings and keep the search form filled.
    return render_template(
        "skills/browse.html",
        listings=listings,
        keyword=keyword,
        listing_type=listing_type,
    )
