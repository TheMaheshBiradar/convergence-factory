package com.acme.billing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.data.jpa.repository.Query;

public class Billing {

    // topic comes from config -> resolves MED (via application.yml)
    @Value("${kafka.topic.order}")
    private String orderTopic;

    private KafkaTemplate<String, String> kafkaTemplate;

    public void emit(String order) {
        kafkaTemplate.send(orderTopic, order);
    }

    @Query("SELECT c FROM customers c WHERE c.active = true")
    public Object activeCustomers() {
        return null;
    }
}
