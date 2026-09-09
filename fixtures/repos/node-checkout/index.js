const { Kafka } = require("kafkajs");
const axios = require("axios");

const ORDER_TOPIC = "order.created";

async function checkout(producer, order) {
  // Publishes the same event as the Java and Python order services — a
  // cross-language duplicate the integration probe should catch.
  await producer.send({ topic: ORDER_TOPIC, messages: [{ value: JSON.stringify(order) }] });
  await axios.get("http://pricing/api/quote");
}

module.exports = { checkout };
