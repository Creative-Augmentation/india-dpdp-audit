<?php
// Illustrative source fixture. This file is not a working WordPress plugin.
add_filter('wp_privacy_personal_data_erasers', 'fixture_erasers');
function fixture_erasers($erasers) {
    $erasers['fixture-notes'] = ['callback' => 'erase_local_fixture_notes'];
    return $erasers;
}
// Data map also lists an external delivery-notes copy keyed by order marker.
