import os
import shutil
import tempfile
import unittest

from convergence_factory.plugins.lang_java import JavaPlugin


class TestJavaCoupling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_single_file_java_coupling_is_zero(self):
        java_file = os.path.join(self.temp_dir, "Main.java")
        with open(java_file, "w") as f:
            f.write("package com.acme;\npublic class Main {}\n")
        self.assertEqual(JavaPlugin._coupling(self.temp_dir), 0.0)

    def test_multiclass_java_coupling(self):
        src_dir = os.path.join(self.temp_dir, "src", "main", "java", "com", "acme")
        client_dir = os.path.join(src_dir, "client")
        os.makedirs(client_dir)

        # File 1: Order.java
        with open(os.path.join(src_dir, "Order.java"), "w") as f:
            f.write("package com.acme;\npublic class Order {}\n")

        # File 2: PaymentClient.java
        with open(os.path.join(client_dir, "PaymentClient.java"), "w") as f:
            f.write("package com.acme.client;\npublic class PaymentClient {}\n")

        # File 3: OrderService.java (references Order in same pkg, imports PaymentClient)
        with open(os.path.join(src_dir, "OrderService.java"), "w") as f:
            f.write("""package com.acme;
import com.acme.client.PaymentClient;

public class OrderService {
    private PaymentClient client;
    public void process(Order order) {}
}
""")

        # 3 files -> max directed edges = 3*2 = 6
        # OrderService -> Order (1)
        # OrderService -> PaymentClient (1)
        # 2 / 6 = 0.333
        coupling = JavaPlugin._coupling(self.temp_dir)
        self.assertEqual(coupling, 0.333)

    def test_wildcard_import_matching(self):
        model_dir = os.path.join(self.temp_dir, "model")
        svc_dir = os.path.join(self.temp_dir, "service")
        os.makedirs(model_dir)
        os.makedirs(svc_dir)

        with open(os.path.join(model_dir, "User.java"), "w") as f:
            f.write("package model;\npublic class User {}\n")

        with open(os.path.join(svc_dir, "UserService.java"), "w") as f:
            f.write("""package service;
import model.*;
public class UserService {
    private User user;
}
""")

        # 2 files -> max directed edges = 2*1 = 2
        # UserService -> User = 1 edge -> 1/2 = 0.5
        coupling = JavaPlugin._coupling(self.temp_dir)
        self.assertEqual(coupling, 0.5)


if __name__ == "__main__":
    unittest.main()
