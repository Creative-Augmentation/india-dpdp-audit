<?php
function demo_pickup_opt_in($order_owner, $callback_number) {
    update_user_meta($order_owner, 'demo_pickup_phone', $callback_number);
}
