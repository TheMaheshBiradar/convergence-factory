package com.acme.inventory;

import org.springframework.kafka.core.KafkaTemplate;

public class Inventory {

    static final String TOPIC = "inventory.updated";   // literal constant -> HIGH

    private KafkaTemplate<String, String> kafkaTemplate;

    public void emit(String event) {
        kafkaTemplate.send(TOPIC, event);
    }
}
