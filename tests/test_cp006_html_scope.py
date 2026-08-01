from backend.retrieval.guidelines.parsers import parse_html


def test_html_parser_discards_noise_outside_main_content() -> None:
    sections = parse_html(
        """
        <div>Explore This Topic Search Duplicate Menu</div>
        <main>
          <h1>Activity guidance</h1>
          <p>Keep the recommendation and its numerical conditions intact.</p>
          <h2>Safety</h2>
          <p>Do not remove the negative safety qualifier.</p>
        </main>
        <div>Share Related Content Back to top</div>
        """
    )

    content = " ".join(section.text for section in sections)
    assert "numerical conditions" in content
    assert "Do not remove" in content
    assert "Explore This Topic" not in content
    assert "Duplicate Menu" not in content
    assert "Share Related Content" not in content
    assert sections[-1].path == ("Activity guidance", "Safety")


def test_html_parser_falls_back_when_document_has_no_main_element() -> None:
    sections = parse_html("<h1>Guidance</h1><p>Fallback content remains available.</p>")
    assert sections[0].path == ("Guidance",)
    assert sections[0].text == "Fallback content remains available."
