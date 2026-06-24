/*
Query 1: Active subscribers with MO traffic in the report window.

Output:
{
  service_type: "Active Subscriber",
  charge_type: "Total Active Subscriber Current",
  total: 9118
}

Equivalent PostgreSQL:

SELECT 'Active Subscriber' AS service_type, 'Total Active Subscriber Current' AS charge_type, COUNT(DISTINCT t.msisdn) AS total FROM iot_portal_tb_usage_log t WHERE t.usage_start_time >= '2026-04-01' AND t.usage_start_time < '2026-05-01' AND t.act_usage_unit > 0;
*/

db.usage_logs.aggregate([
  {
    $match: {
      usage_start_time: {
        $gte: ISODate("{{start_date}}"),
        $lt: ISODate("{{end_date}}")
      },
      act_usage_unit: { $gt: 0 }
    }
  },
  {
    $addFields: {
      msisdn_trimmed: {
        $trim: {
          input: { $toString: "$msisdn" }
        }
      }
    }
  },
  {
    $match: {
      msisdn: { $exists: true, $ne: null }
    }
  },
  {
    $match: {
      msisdn_trimmed: { $ne: "" }
    }
  },
  {
    $group: {
      _id: "$msisdn_trimmed"
    }
  },
  {
    $group: {
      _id: null,
      total: { $sum: 1 }
    }
  },
  {
    $project: {
      _id: 0,
      service_type: { $literal: "Active Subscriber" },
      charge_type: { $literal: "Total Active Subscriber Current" },
      total: 1
    }
  }
]);
