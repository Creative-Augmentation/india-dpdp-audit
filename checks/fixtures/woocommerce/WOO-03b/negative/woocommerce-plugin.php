<?php
function demo_pickup_opt_in($order_owner, $callback_number) {
    update_user_meta($order_owner, 'demo_pickup_phone', $callback_number);
}
add_filter('wp_privacy_personal_data_erasers', 'demo_pickup_register');
function demo_pickup_register($erasers) {
    $erasers['demo_pickup'] = ['eraser_friendly_name' => 'Demo pickup', 'callback' => 'demo_pickup_erase'];
    return $erasers;
}
